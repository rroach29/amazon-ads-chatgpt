"""Executive Brain v2.0.1 — Registry Linking Engine.

Purpose:
Connect existing business data rows to the canonical Master Product Registry.

This release improves Product Genome usefulness by resolving rows from:
- Seller Central Sales & Traffic
- Amazon Ads campaign details
- Amazon Ads search term details

into:
- master_product_id

The engine is intentionally conservative. It prefers exact SKU/ASIN matches and
only uses text matching as a fallback.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import inspect, text

from database import SessionLocal, engine
from business_registry.models import BusinessEvent, MasterProduct, ProductChannel


class RegistryLinkingService:
    version = "executive-brain-2.0.1"

    @classmethod
    def status(cls) -> dict[str, Any]:
        inspector = inspect(engine)
        tables = {}
        for table in [
            "master_products",
            "product_channels",
            "seller_central_sales_traffic",
            "campaign_daily_details",
            "search_term_daily_details",
        ]:
            if not inspector.has_table(table):
                tables[table] = {"exists": False}
                continue
            columns = {c["name"] for c in inspector.get_columns(table)}
            tables[table] = {
                "exists": True,
                "has_master_product_id": "master_product_id" in columns,
                "columns": sorted([c for c in columns if c in {"master_product_id", "sku", "asin", "campaign_name", "search_term"}]),
            }
        return {"status": "OK", "version": cls.version, "tables": tables}

    @classmethod
    def ensure_columns(cls) -> dict[str, Any]:
        statements = [
            "ALTER TABLE seller_central_sales_traffic ADD COLUMN IF NOT EXISTS master_product_id VARCHAR",
            "CREATE INDEX IF NOT EXISTS ix_seller_central_sales_traffic_master_product_id ON seller_central_sales_traffic (master_product_id)",
            "ALTER TABLE campaign_daily_details ADD COLUMN IF NOT EXISTS master_product_id VARCHAR",
            "CREATE INDEX IF NOT EXISTS ix_campaign_daily_details_master_product_id ON campaign_daily_details (master_product_id)",
            "ALTER TABLE search_term_daily_details ADD COLUMN IF NOT EXISTS master_product_id VARCHAR",
            "CREATE INDEX IF NOT EXISTS ix_search_term_daily_details_master_product_id ON search_term_daily_details (master_product_id)",
        ]
        db = SessionLocal()
        executed = []
        try:
            for stmt in statements:
                db.execute(text(stmt))
                executed.append(stmt)
            db.commit()
            return {"status": "OK", "version": cls.version, "executed": executed, "linking_status": cls.status()}
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc), "executed": executed}
        finally:
            db.close()

    @classmethod
    def summary(cls) -> dict[str, Any]:
        db = SessionLocal()
        try:
            result = {"status": "OK", "version": cls.version, "tables": {}}
            for table in ["seller_central_sales_traffic", "campaign_daily_details", "search_term_daily_details"]:
                if not cls._has_column(table, "master_product_id"):
                    result["tables"][table] = {"migration_required": True}
                    continue
                total = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0
                linked = db.execute(text(f"SELECT COUNT(*) FROM {table} WHERE master_product_id IS NOT NULL")).scalar() or 0
                result["tables"][table] = {
                    "total_rows": total,
                    "linked_rows": linked,
                    "unlinked_rows": total - linked,
                    "linked_pct": round(linked / total, 4) if total else None,
                }
            return result
        finally:
            db.close()

    @classmethod
    def link_all(cls, dry_run: bool = True, limit: int = 10000) -> dict[str, Any]:
        return {
            "status": "DRY_RUN" if dry_run else "UPDATED",
            "version": cls.version,
            "seller_central": cls.link_seller_central(dry_run=dry_run, limit=limit),
            "campaign_details": cls.link_campaign_details(dry_run=dry_run, limit=limit),
            "search_terms": cls.link_search_terms(dry_run=dry_run, limit=limit),
            "summary_after": cls.summary() if not dry_run else "not_updated_dry_run",
        }

    @classmethod
    def link_seller_central(cls, dry_run: bool = True, limit: int = 10000) -> dict[str, Any]:
        return cls._link_table(
            table="seller_central_sales_traffic",
            resolver_name="seller_central",
            dry_run=dry_run,
            limit=limit,
        )

    @classmethod
    def link_campaign_details(cls, dry_run: bool = True, limit: int = 10000) -> dict[str, Any]:
        return cls._link_table(
            table="campaign_daily_details",
            resolver_name="amazon_ads",
            dry_run=dry_run,
            limit=limit,
        )

    @classmethod
    def link_search_terms(cls, dry_run: bool = True, limit: int = 10000) -> dict[str, Any]:
        return cls._link_table(
            table="search_term_daily_details",
            resolver_name="amazon_ads",
            dry_run=dry_run,
            limit=limit,
        )

    @classmethod
    def _link_table(cls, table: str, resolver_name: str, dry_run: bool, limit: int) -> dict[str, Any]:
        db = SessionLocal()
        try:
            if not cls._has_column(table, "master_product_id"):
                return {"status": "MIGRATION_REQUIRED", "table": table, "next_step": "POST /business-os/registry/linking/ensure-columns"}

            safe_limit = max(1, min(limit, 50000))
            rows = db.execute(text(f"SELECT * FROM {table} WHERE master_product_id IS NULL LIMIT :limit"), {"limit": safe_limit}).mappings().all()

            linked = 0
            unlinked = 0
            samples = []
            methods = {}

            for row in rows:
                match = cls._resolve_safely(db, row=row, resolver_name=resolver_name)
                if match:
                    linked += 1
                    methods[match["matched_by"]] = methods.get(match["matched_by"], 0) + 1
                    if not dry_run:
                        db.execute(
                            text(f"UPDATE {table} SET master_product_id = :mpid WHERE id = :id"),
                            {"mpid": match["master_product_id"], "id": row["id"]},
                        )
                    if len(samples) < 30:
                        samples.append({
                            "row_id": row.get("id"),
                            "master_product_id": match["master_product_id"],
                            "matched_by": match["matched_by"],
                            "sku": row.get("sku"),
                            "asin": row.get("asin"),
                            "campaign_name": row.get("campaign_name"),
                            "search_term": row.get("search_term"),
                        })
                else:
                    unlinked += 1

            if not dry_run:
                cls._record_event(
                    db,
                    title=f"Registry Linking completed for {table}",
                    description=f"Linked {linked} rows in {table} to Master Product IDs.",
                    payload={"table": table, "linked": linked, "unlinked": unlinked, "methods": methods},
                )
                db.commit()

            return {
                "status": "DRY_RUN" if dry_run else "UPDATED",
                "version": cls.version,
                "table": table,
                "rows_checked": len(rows),
                "linked": linked,
                "unlinked": unlinked,
                "match_methods": methods,
                "sample_matches": samples,
                "dry_run": dry_run,
            }
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "table": table, "message": str(exc)}
        finally:
            db.close()

    @classmethod
    def resolve(cls, sku: str | None = None, asin: str | None = None, text_value: str | None = None) -> dict[str, Any]:
        db = SessionLocal()
        try:
            match = cls._resolve_identifiers(db, sku=sku, asin=asin, text_value=text_value)
            return {
                "status": "OK" if match else "NOT_FOUND",
                "version": cls.version,
                "match": match,
                "input": {"sku": sku, "asin": asin, "text_value": text_value},
            }
        finally:
            db.close()

    @classmethod
    def _resolve_safely(cls, db, row: dict, resolver_name: str) -> dict[str, str] | None:
        if resolver_name == "seller_central":
            return cls._resolve_identifiers(db, sku=row.get("sku"), asin=row.get("asin"))

        raw = row.get("raw") or {}
        raw_text = str(raw)

        # Exact identifiers from raw payload if available.
        for key in ["sku", "advertisedSku", "purchasedSku"]:
            value = cls._raw_get(raw, key)
            match = cls._resolve_identifiers(db, sku=value)
            if match:
                match["matched_by"] = f"raw.{key}"
                return match

        for key in ["asin", "advertisedAsin", "purchasedAsin"]:
            value = cls._raw_get(raw, key)
            match = cls._resolve_identifiers(db, asin=value)
            if match:
                match["matched_by"] = f"raw.{key}"
                return match

        # Fallback text matching from campaign/search-term context.
        text_value = " ".join([
            str(row.get("campaign_name") or ""),
            str(row.get("ad_group_name") or ""),
            str(row.get("keyword") or ""),
            str(row.get("search_term") or ""),
            raw_text,
        ])
        return cls._resolve_identifiers(db, text_value=text_value)

    @classmethod
    def _resolve_identifiers(cls, db, sku: str | None = None, asin: str | None = None, text_value: str | None = None) -> dict[str, str] | None:
        sku = cls._clean(sku)
        asin = cls._clean(asin)

        if sku:
            product = db.query(MasterProduct).filter(MasterProduct.primary_sku == sku).first()
            if product:
                return {"master_product_id": product.master_product_id, "matched_by": "master_products.primary_sku"}

            channel = db.query(ProductChannel).filter(ProductChannel.sku == sku).first()
            if channel:
                return {"master_product_id": channel.master_product_id, "matched_by": "product_channels.sku"}

        if asin:
            channel = db.query(ProductChannel).filter(ProductChannel.asin == asin).first()
            if channel:
                return {"master_product_id": channel.master_product_id, "matched_by": "product_channels.asin"}

            channel = db.query(ProductChannel).filter(ProductChannel.channel_product_id == asin).first()
            if channel:
                return {"master_product_id": channel.master_product_id, "matched_by": "product_channels.channel_product_id"}

        if text_value:
            text_lower = str(text_value).lower()
            # First try exact SKU token containment.
            products = db.query(MasterProduct).all()
            for product in products:
                sku_token = cls._clean(product.primary_sku)
                if sku_token and sku_token.lower() in text_lower:
                    return {"master_product_id": product.master_product_id, "matched_by": "text.primary_sku"}

            # Then conservative product-name token overlap.
            for product in products:
                tokens = cls._tokens(product.name)
                strong_tokens = [t for t in tokens if len(t) >= 6]
                if strong_tokens and any(t in text_lower for t in strong_tokens):
                    return {"master_product_id": product.master_product_id, "matched_by": "text.product_name_token"}

        return None

    @staticmethod
    def _raw_get(raw: Any, key: str):
        if isinstance(raw, dict):
            return raw.get(key)
        return None

    @staticmethod
    def _has_column(table: str, column: str) -> bool:
        inspector = inspect(engine)
        if not inspector.has_table(table):
            return False
        return column in {c["name"] for c in inspector.get_columns(table)}

    @staticmethod
    def _clean(value: Any) -> str | None:
        if value is None:
            return None
        text_value = str(value).strip()
        return text_value or None

    @staticmethod
    def _tokens(value: Any) -> set[str]:
        if not value:
            return set()
        stopwords = {"the", "and", "for", "with", "case", "gift", "handmade", "perfect", "durable"}
        parts = str(value).lower().replace("-", " ").replace("_", " ").replace(":", " ").split()
        return {p.strip(".,!()[]{}") for p in parts if len(p.strip(".,!()[]{}")) >= 4 and p not in stopwords}

    @staticmethod
    def _record_event(db, title: str, description: str, payload: dict[str, Any]):
        db.add(
            BusinessEvent(
                event_id=f"EV-{uuid4().hex[:12].upper()}",
                event_type="RegistryLinking",
                occurred_at=datetime.utcnow(),
                title=title,
                description=description,
                source="registry_linking_engine",
                payload=payload,
            )
        )
