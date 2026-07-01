"""Business Core v1.1.1 — Registry Resolver hotfix.

Fixes v1.1 runtime error:
- imports datetime correctly for event generation.

Attaches Master Product IDs to existing Amazon Ads and Seller Central rows where
the data contains a resolvable SKU, ASIN, or channel identifier.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import inspect, text

from database import SessionLocal, engine
from models import CampaignDailyDetail, SearchTermDailyDetail, SellerCentralSalesTraffic
from business_registry.models import MasterProduct, ProductChannel, BusinessEvent


class RegistryResolverService:
    version = "business-core-1.1.1"

    @staticmethod
    def migration_status() -> dict[str, Any]:
        inspector = inspect(engine)
        tables = {}
        for table in ["campaign_daily_details", "search_term_daily_details", "seller_central_sales_traffic"]:
            if not inspector.has_table(table):
                tables[table] = {"exists": False, "has_master_product_id": False}
                continue
            columns = {c["name"] for c in inspector.get_columns(table)}
            tables[table] = {
                "exists": True,
                "has_master_product_id": "master_product_id" in columns,
                "columns_checked": ["master_product_id"],
            }
        return {"status": "OK", "version": RegistryResolverService.version, "tables": tables}

    @staticmethod
    def ensure_registry_columns() -> dict[str, Any]:
        statements = [
            "ALTER TABLE campaign_daily_details ADD COLUMN IF NOT EXISTS master_product_id VARCHAR",
            "CREATE INDEX IF NOT EXISTS ix_campaign_daily_details_master_product_id ON campaign_daily_details (master_product_id)",
            "ALTER TABLE search_term_daily_details ADD COLUMN IF NOT EXISTS master_product_id VARCHAR",
            "CREATE INDEX IF NOT EXISTS ix_search_term_daily_details_master_product_id ON search_term_daily_details (master_product_id)",
            "ALTER TABLE seller_central_sales_traffic ADD COLUMN IF NOT EXISTS master_product_id VARCHAR",
            "CREATE INDEX IF NOT EXISTS ix_seller_central_sales_traffic_master_product_id ON seller_central_sales_traffic (master_product_id)",
        ]
        db = SessionLocal()
        executed = []
        try:
            for stmt in statements:
                db.execute(text(stmt))
                executed.append(stmt)
            db.commit()
            return {
                "status": "OK",
                "version": RegistryResolverService.version,
                "executed": executed,
                "migration_status": RegistryResolverService.migration_status(),
            }
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": RegistryResolverService.version, "message": str(exc), "executed": executed}
        finally:
            db.close()

    @staticmethod
    def resolve_identifier(
        sku: str | None = None,
        asin: str | None = None,
        channel: str | None = None,
        channel_product_id: str | None = None,
        channel_listing_id: str | None = None,
    ) -> dict[str, Any]:
        db = SessionLocal()
        try:
            result = RegistryResolverService._resolve_with_db(
                db,
                sku=sku,
                asin=asin,
                channel=channel,
                channel_product_id=channel_product_id,
                channel_listing_id=channel_listing_id,
            )
            return {
                "status": "OK" if result else "NOT_FOUND",
                "version": RegistryResolverService.version,
                "master_product_id": result,
                "input": {
                    "sku": sku,
                    "asin": asin,
                    "channel": channel,
                    "channel_product_id": channel_product_id,
                    "channel_listing_id": channel_listing_id,
                },
            }
        finally:
            db.close()

    @staticmethod
    def backfill_seller_central(dry_run: bool = True, limit: int = 5000) -> dict[str, Any]:
        return RegistryResolverService._backfill_table(
            table_name="seller_central_sales_traffic",
            row_model=SellerCentralSalesTraffic,
            resolver="seller_central",
            dry_run=dry_run,
            limit=limit,
        )

    @staticmethod
    def backfill_campaign_details(dry_run: bool = True, limit: int = 5000) -> dict[str, Any]:
        return RegistryResolverService._backfill_table(
            table_name="campaign_daily_details",
            row_model=CampaignDailyDetail,
            resolver="ad_row",
            dry_run=dry_run,
            limit=limit,
        )

    @staticmethod
    def backfill_search_terms(dry_run: bool = True, limit: int = 5000) -> dict[str, Any]:
        return RegistryResolverService._backfill_table(
            table_name="search_term_daily_details",
            row_model=SearchTermDailyDetail,
            resolver="ad_row",
            dry_run=dry_run,
            limit=limit,
        )

    @staticmethod
    def _backfill_table(table_name: str, row_model, resolver: str, dry_run: bool, limit: int) -> dict[str, Any]:
        db = SessionLocal()
        try:
            if not RegistryResolverService._has_column(table_name, "master_product_id"):
                return {
                    "status": "MIGRATION_REQUIRED",
                    "version": RegistryResolverService.version,
                    "table": table_name,
                    "next_step": "Run POST /business-os/registry/integration/ensure-columns",
                }

            safe_limit = max(1, min(limit, 20000))
            rows = (
                db.query(row_model)
                .from_statement(text(f"SELECT * FROM {table_name} WHERE master_product_id IS NULL LIMIT :limit"))
                .params(limit=safe_limit)
                .all()
            )

            resolved = 0
            unresolved = 0
            samples = []

            for row in rows:
                if resolver == "seller_central":
                    mpid = RegistryResolverService._resolve_with_db(db, sku=getattr(row, "sku", None), asin=getattr(row, "asin", None), channel="Amazon")
                else:
                    mpid = RegistryResolverService._resolve_from_ad_row(db, row)

                if mpid:
                    resolved += 1
                    if not dry_run:
                        db.execute(
                            text(f"UPDATE {table_name} SET master_product_id = :mpid WHERE id = :id"),
                            {"mpid": mpid, "id": row.id},
                        )
                    if len(samples) < 25:
                        samples.append(RegistryResolverService._sample_row(table_name, row, mpid))
                else:
                    unresolved += 1

            if not dry_run:
                db.commit()
                RegistryResolverService._record_event(
                    db,
                    event_type="RegistryBackfill",
                    title=f"{table_name} rows resolved to Master Products",
                    description=f"Resolved {resolved} rows in {table_name} to Master Product IDs.",
                    payload={"table": table_name, "resolved": resolved, "unresolved": unresolved, "dry_run": dry_run},
                )
                db.commit()

            return {
                "status": "DRY_RUN" if dry_run else "UPDATED",
                "version": RegistryResolverService.version,
                "table": table_name,
                "rows_checked": len(rows),
                "resolved": resolved,
                "unresolved": unresolved,
                "sample_matches": samples,
                "dry_run": dry_run,
            }
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": RegistryResolverService.version, "table": table_name, "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def integration_summary() -> dict[str, Any]:
        db = SessionLocal()
        try:
            summary = {"status": "OK", "version": RegistryResolverService.version, "tables": {}}
            for table_name in ["seller_central_sales_traffic", "campaign_daily_details", "search_term_daily_details"]:
                if not RegistryResolverService._has_column(table_name, "master_product_id"):
                    summary["tables"][table_name] = {"migration_required": True}
                    continue
                total = db.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0
                resolved = db.execute(text(f"SELECT COUNT(*) FROM {table_name} WHERE master_product_id IS NOT NULL")).scalar() or 0
                summary["tables"][table_name] = {
                    "total_rows": total,
                    "resolved_rows": resolved,
                    "unresolved_rows": total - resolved,
                    "resolved_pct": round(resolved / total, 4) if total else None,
                }
            return summary
        finally:
            db.close()

    @staticmethod
    def _resolve_with_db(
        db,
        sku: str | None = None,
        asin: str | None = None,
        channel: str | None = None,
        channel_product_id: str | None = None,
        channel_listing_id: str | None = None,
    ) -> str | None:
        sku = RegistryResolverService._clean(sku)
        asin = RegistryResolverService._clean(asin)
        channel_product_id = RegistryResolverService._clean(channel_product_id)
        channel_listing_id = RegistryResolverService._clean(channel_listing_id)

        if sku:
            mp = db.query(MasterProduct).filter(MasterProduct.primary_sku == sku).first()
            if mp:
                return mp.master_product_id
            ch = db.query(ProductChannel).filter(ProductChannel.sku == sku).first()
            if ch:
                return ch.master_product_id

        if asin:
            ch = db.query(ProductChannel).filter(ProductChannel.asin == asin).first()
            if ch:
                return ch.master_product_id

        if channel_product_id:
            q = db.query(ProductChannel).filter(ProductChannel.channel_product_id == channel_product_id)
            if channel:
                q = q.filter(ProductChannel.channel.ilike(f"%{channel}%"))
            ch = q.first()
            if ch:
                return ch.master_product_id

        if channel_listing_id:
            q = db.query(ProductChannel).filter(ProductChannel.channel_listing_id == channel_listing_id)
            if channel:
                q = q.filter(ProductChannel.channel.ilike(f"%{channel}%"))
            ch = q.first()
            if ch:
                return ch.master_product_id

        return None

    @staticmethod
    def _resolve_from_ad_row(db, row) -> str | None:
        raw = row.raw if isinstance(row.raw, dict) else {}
        explicit_pairs = [
            ("sku", raw.get("sku")),
            ("sku", raw.get("advertisedSku")),
            ("sku", raw.get("purchasedSku")),
            ("asin", raw.get("asin")),
            ("asin", raw.get("advertisedAsin")),
            ("asin", raw.get("purchasedAsin")),
        ]
        for kind, value in explicit_pairs:
            if kind == "sku":
                mpid = RegistryResolverService._resolve_with_db(db, sku=value, channel="Amazon")
            else:
                mpid = RegistryResolverService._resolve_with_db(db, asin=value, channel="Amazon")
            if mpid:
                return mpid

        text_blob = " ".join([
            str(getattr(row, "campaign_name", "") or ""),
            str(getattr(row, "ad_group_name", "") or ""),
            str(raw),
        ]).lower()

        products = db.query(MasterProduct).all()
        for product in products:
            tokens = RegistryResolverService._tokens(product.primary_sku) | RegistryResolverService._tokens(product.name)
            if tokens and any(token in text_blob for token in tokens if len(token) >= 4):
                return product.master_product_id

        return None

    @staticmethod
    def _record_event(db, event_type: str, title: str, description: str, payload: dict[str, Any]):
        db.add(
            BusinessEvent(
                event_id=f"EV-{uuid4().hex[:12].upper()}",
                event_type=event_type,
                title=title,
                description=description,
                source="registry_resolver",
                payload=payload,
            )
        )

    @staticmethod
    def _sample_row(table_name: str, row, mpid: str) -> dict[str, Any]:
        sample = {"row_id": getattr(row, "id", None), "master_product_id": mpid}
        for field in ["sku", "asin", "campaign_name", "search_term", "date"]:
            if hasattr(row, field):
                value = getattr(row, field)
                sample[field] = value.isoformat() if hasattr(value, "isoformat") else value
        sample["table"] = table_name
        return sample

    @staticmethod
    def _has_column(table: str, column: str) -> bool:
        inspector = inspect(engine)
        if not inspector.has_table(table):
            return False
        return column in {c["name"] for c in inspector.get_columns(table)}

    @staticmethod
    def _tokens(value: Any) -> set[str]:
        if not value:
            return set()
        return {part.strip().lower() for part in str(value).replace("-", " ").replace("_", " ").split() if len(part.strip()) >= 4}

    @staticmethod
    def _clean(value: Any) -> str | None:
        if value is None:
            return None
        text_value = str(value).strip()
        return text_value or None
