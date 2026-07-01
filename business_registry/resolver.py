"""Business Core v1.1 — Registry Resolver.

Attaches Master Product IDs to existing Amazon Ads and Seller Central rows where
the data contains a resolvable SKU, ASIN, or channel identifier.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import inspect, text

from database import SessionLocal, engine
from models import CampaignDailyDetail, SearchTermDailyDetail, SellerCentralSalesTraffic
from business_registry.models import MasterProduct, ProductChannel, BusinessEvent


class RegistryResolverService:
    version = "business-core-1.1"

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
        """Adds nullable master_product_id columns to existing data tables.

        PostgreSQL syntax is used because the production app is on Render/Postgres.
        """
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
        db = SessionLocal()
        try:
            if not RegistryResolverService._has_column("seller_central_sales_traffic", "master_product_id"):
                return {"status": "MIGRATION_REQUIRED", "version": RegistryResolverService.version, "next_step": "Run POST /business-os/registry/integration/ensure-columns"}

            rows = (
                db.query(SellerCentralSalesTraffic)
                .from_statement(text("SELECT * FROM seller_central_sales_traffic WHERE master_product_id IS NULL LIMIT :limit")).params(limit=max(1, min(limit, 20000))).all()
            )
            resolved = 0
            unresolved = 0
            samples = []

            for row in rows:
                mpid = RegistryResolverService._resolve_with_db(
                    db,
                    sku=row.sku,
                    asin=row.asin,
                    channel="Amazon",
                )
                if mpid:
                    resolved += 1
                    if not dry_run:
                        db.execute(text("UPDATE seller_central_sales_traffic SET master_product_id = :mpid WHERE id = :id"), {"mpid": mpid, "id": row.id})
                    if len(samples) < 25:
                        samples.append({"row_id": row.id, "sku": row.sku, "asin": row.asin, "master_product_id": mpid})
                else:
                    unresolved += 1

            if not dry_run:
                db.commit()
                RegistryResolverService._record_event(
                    db,
                    event_type="RegistryBackfill",
                    title="Seller Central rows resolved to Master Products",
                    description=f"Resolved {resolved} Seller Central rows to Master Product IDs.",
                    payload={"resolved": resolved, "unresolved": unresolved, "dry_run": dry_run},
                )
                db.commit()

            return {
                "status": "DRY_RUN" if dry_run else "UPDATED",
                "version": RegistryResolverService.version,
                "table": "seller_central_sales_traffic",
                "rows_checked": len(rows),
                "resolved": resolved,
                "unresolved": unresolved,
                "sample_matches": samples,
                "dry_run": dry_run,
            }
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": RegistryResolverService.version, "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def backfill_campaign_details(dry_run: bool = True, limit: int = 5000) -> dict[str, Any]:
        db = SessionLocal()
        try:
            if not RegistryResolverService._has_column("campaign_daily_details", "master_product_id"):
                return {"status": "MIGRATION_REQUIRED", "version": RegistryResolverService.version, "next_step": "Run POST /business-os/registry/integration/ensure-columns"}

            rows = (
                db.query(CampaignDailyDetail)
                .from_statement(text("SELECT * FROM campaign_daily_details WHERE master_product_id IS NULL LIMIT :limit")).params(limit=max(1, min(limit, 20000))).all()
            )

            resolved = 0
            unresolved = 0
            samples = []
            for row in rows:
                mpid = RegistryResolverService._resolve_from_ad_row(db, row)
                if mpid:
                    resolved += 1
                    if not dry_run:
                        db.execute(text("UPDATE campaign_daily_details SET master_product_id = :mpid WHERE id = :id"), {"mpid": mpid, "id": row.id})
                    if len(samples) < 25:
                        samples.append({"row_id": row.id, "campaign_name": row.campaign_name, "master_product_id": mpid})
                else:
                    unresolved += 1

            if not dry_run:
                db.commit()
                RegistryResolverService._record_event(
                    db,
                    event_type="RegistryBackfill",
                    title="Campaign rows resolved to Master Products",
                    description=f"Resolved {resolved} campaign detail rows to Master Product IDs.",
                    payload={"resolved": resolved, "unresolved": unresolved, "dry_run": dry_run},
                )
                db.commit()

            return {
                "status": "DRY_RUN" if dry_run else "UPDATED",
                "version": RegistryResolverService.version,
                "table": "campaign_daily_details",
                "rows_checked": len(rows),
                "resolved": resolved,
                "unresolved": unresolved,
                "sample_matches": samples,
                "dry_run": dry_run,
                "note": "Campaign matching uses explicit ASIN/SKU fields in raw payload when available, then conservative SKU/name token matching.",
            }
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": RegistryResolverService.version, "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def backfill_search_terms(dry_run: bool = True, limit: int = 5000) -> dict[str, Any]:
        db = SessionLocal()
        try:
            if not RegistryResolverService._has_column("search_term_daily_details", "master_product_id"):
                return {"status": "MIGRATION_REQUIRED", "version": RegistryResolverService.version, "next_step": "Run POST /business-os/registry/integration/ensure-columns"}

            rows = (
                db.query(SearchTermDailyDetail)
                .from_statement(text("SELECT * FROM search_term_daily_details WHERE master_product_id IS NULL LIMIT :limit")).params(limit=max(1, min(limit, 20000))).all()
            )

            resolved = 0
            unresolved = 0
            samples = []
            for row in rows:
                mpid = RegistryResolverService._resolve_from_ad_row(db, row)
                if mpid:
                    resolved += 1
                    if not dry_run:
                        db.execute(text("UPDATE search_term_daily_details SET master_product_id = :mpid WHERE id = :id"), {"mpid": mpid, "id": row.id})
                    if len(samples) < 25:
                        samples.append({"row_id": row.id, "campaign_name": row.campaign_name, "search_term": row.search_term, "master_product_id": mpid})
                else:
                    unresolved += 1

            if not dry_run:
                db.commit()
                RegistryResolverService._record_event(
                    db,
                    event_type="RegistryBackfill",
                    title="Search term rows resolved to Master Products",
                    description=f"Resolved {resolved} search term detail rows to Master Product IDs.",
                    payload={"resolved": resolved, "unresolved": unresolved, "dry_run": dry_run},
                )
                db.commit()

            return {
                "status": "DRY_RUN" if dry_run else "UPDATED",
                "version": RegistryResolverService.version,
                "table": "search_term_daily_details",
                "rows_checked": len(rows),
                "resolved": resolved,
                "unresolved": unresolved,
                "sample_matches": samples,
                "dry_run": dry_run,
            }
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": RegistryResolverService.version, "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def integration_summary() -> dict[str, Any]:
        db = SessionLocal()
        try:
            summary = {"status": "OK", "version": RegistryResolverService.version, "tables": {}}
            for model, table_name in [
                (SellerCentralSalesTraffic, "seller_central_sales_traffic"),
                (CampaignDailyDetail, "campaign_daily_details"),
                (SearchTermDailyDetail, "search_term_daily_details"),
            ]:
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
        explicit_values = [
            raw.get("sku"),
            raw.get("advertisedSku"),
            raw.get("purchasedSku"),
            raw.get("asin"),
            raw.get("advertisedAsin"),
            raw.get("purchasedAsin"),
        ]
        for value in explicit_values:
            mpid = RegistryResolverService._resolve_with_db(db, sku=value, asin=value, channel="Amazon")
            if mpid:
                return mpid

        # Conservative fallback: match registry SKU/name tokens in campaign name.
        text = " ".join([
            str(row.campaign_name or ""),
            str(getattr(row, "ad_group_name", "") or ""),
            str(raw),
        ]).lower()

        products = db.query(MasterProduct).all()
        for product in products:
            tokens = RegistryResolverService._tokens(product.primary_sku) | RegistryResolverService._tokens(product.name)
            if tokens and any(token in text for token in tokens if len(token) >= 4):
                return product.master_product_id

        return None

    @staticmethod
    def _record_event(db, event_type: str, title: str, description: str, payload: dict[str, Any]):
        db.add(
            BusinessEvent(
                event_id=f"EV-BACKFILL-{abs(hash(title + str(payload) + str(datetime.utcnow()))) % 10_000_000_000}",
                event_type=event_type,
                title=title,
                description=description,
                source="registry_resolver",
                payload=payload,
            )
        )

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
        text = str(value).strip()
        return text or None
