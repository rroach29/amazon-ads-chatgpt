"""Amazon Product Identity Sync.

Populates Amazon ProductChannel identity mappings from existing Seller Central
Sales & Traffic rows. This makes ASIN/SKU/marketplace available to Product
Workspace, ChangeSets, and Mission Control without requiring manual entry.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func

from database import SessionLocal
from models import SellerCentralSalesTraffic
from business_registry.models import MasterProduct, ProductChannel, BusinessEvent


class AmazonIdentitySyncService:
    version = "business-os-0.7.1-amazon-identity-sync"

    @classmethod
    def sync_from_seller_central(cls, dry_run: bool = True, limit: int = 1000) -> dict[str, Any]:
        db = SessionLocal()
        try:
            rows = (
                db.query(
                    SellerCentralSalesTraffic.asin,
                    SellerCentralSalesTraffic.sku,
                    SellerCentralSalesTraffic.title,
                    SellerCentralSalesTraffic.country_code,
                    SellerCentralSalesTraffic.marketplace,
                    SellerCentralSalesTraffic.currency,
                    func.max(SellerCentralSalesTraffic.date).label("last_seen"),
                )
                .filter((SellerCentralSalesTraffic.asin.isnot(None)) | (SellerCentralSalesTraffic.sku.isnot(None)))
                .group_by(
                    SellerCentralSalesTraffic.asin,
                    SellerCentralSalesTraffic.sku,
                    SellerCentralSalesTraffic.title,
                    SellerCentralSalesTraffic.country_code,
                    SellerCentralSalesTraffic.marketplace,
                    SellerCentralSalesTraffic.currency,
                )
                .order_by(func.max(SellerCentralSalesTraffic.date).desc())
                .limit(max(1, min(limit, 10000)))
                .all()
            )

            created_products = 0
            created_channels = 0
            updated_channels = 0
            skipped = 0
            samples = []

            for row in rows:
                asin = cls._clean(row.asin)
                sku = cls._clean(row.sku)
                if not asin and not sku:
                    skipped += 1
                    continue

                product = cls._resolve_product(db, sku=sku, asin=asin, title=row.title)
                product_created = False
                if not product:
                    product_created = True
                    product = cls._new_master_product(sku=sku, asin=asin, title=row.title)
                    if not dry_run:
                        db.add(product)
                        db.flush()
                    created_products += 1

                channel = cls._resolve_channel(db, master_product_id=product.master_product_id, sku=sku, asin=asin, marketplace=row.country_code or row.marketplace)
                action = "none"
                if not channel:
                    channel = ProductChannel(
                        master_product_id=product.master_product_id,
                        brand=product.brand,
                        primary_sku=product.primary_sku,
                        channel="Amazon",
                        marketplace=row.country_code or row.marketplace,
                        currency=row.currency,
                        channel_product_id=asin,
                        channel_listing_id=asin,
                        asin=asin,
                        sku=sku,
                        status="Mapped",
                        raw=cls._raw(row),
                    )
                    action = "create_channel"
                    created_channels += 1
                    if not dry_run:
                        db.add(channel)
                else:
                    changed = False
                    for attr, value in {
                        "asin": asin,
                        "sku": sku,
                        "channel_product_id": asin,
                        "channel_listing_id": asin,
                        "marketplace": row.country_code or row.marketplace,
                        "currency": row.currency,
                        "status": "Mapped",
                    }.items():
                        if value and getattr(channel, attr, None) != value:
                            setattr(channel, attr, value)
                            changed = True
                    raw = channel.raw if isinstance(channel.raw, dict) else {}
                    raw.update(cls._raw(row))
                    channel.raw = raw
                    if changed:
                        channel.updated_at = datetime.utcnow()
                        updated_channels += 1
                        action = "update_channel"

                if len(samples) < 50:
                    samples.append({
                        "action": action,
                        "product_created": product_created,
                        "master_product_id": product.master_product_id,
                        "product_name": product.name,
                        "sku": sku,
                        "asin": asin,
                        "marketplace": row.country_code or row.marketplace,
                        "last_seen": row.last_seen.isoformat() if row.last_seen else None,
                    })

            if not dry_run:
                db.add(BusinessEvent(
                    event_id=f"EV-{uuid4().hex[:12].upper()}",
                    event_type="AmazonIdentitySync",
                    title="Amazon ASIN/SKU identity sync completed",
                    description=f"Created {created_channels} channels, updated {updated_channels} channels, created {created_products} products.",
                    source="amazon_identity_sync",
                    payload={
                        "rows_checked": len(rows),
                        "created_products": created_products,
                        "created_channels": created_channels,
                        "updated_channels": updated_channels,
                        "skipped": skipped,
                    },
                ))
                db.commit()

            return {
                "status": "DRY_RUN" if dry_run else "UPDATED",
                "version": cls.version,
                "source": "seller_central_sales_traffic",
                "rows_checked": len(rows),
                "created_products": created_products,
                "created_channels": created_channels,
                "updated_channels": updated_channels,
                "skipped": skipped,
                "dry_run": dry_run,
                "sample_mappings": samples,
            }
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc), "dry_run": dry_run}
        finally:
            db.close()

    @classmethod
    def summary(cls) -> dict[str, Any]:
        db = SessionLocal()
        try:
            total_amazon_channels = db.query(ProductChannel).filter(ProductChannel.channel.ilike("%Amazon%")).count()
            mapped_asins = db.query(ProductChannel).filter(ProductChannel.channel.ilike("%Amazon%"), ProductChannel.asin.isnot(None)).count()
            mapped_skus = db.query(ProductChannel).filter(ProductChannel.channel.ilike("%Amazon%"), ProductChannel.sku.isnot(None)).count()
            seller_rows = db.query(SellerCentralSalesTraffic).count()
            seller_distinct_asins = db.query(SellerCentralSalesTraffic.asin).filter(SellerCentralSalesTraffic.asin.isnot(None)).distinct().count()
            return {
                "status": "OK",
                "version": cls.version,
                "amazon_channels": total_amazon_channels,
                "amazon_channels_with_asin": mapped_asins,
                "amazon_channels_with_sku": mapped_skus,
                "seller_central_rows": seller_rows,
                "seller_central_distinct_asins": seller_distinct_asins,
                "asin_mapping_pct": round(mapped_asins / total_amazon_channels, 4) if total_amazon_channels else None,
            }
        finally:
            db.close()

    @staticmethod
    def _resolve_product(db, sku: str | None, asin: str | None, title: str | None):
        if sku:
            product = db.query(MasterProduct).filter(MasterProduct.primary_sku == sku).first()
            if product:
                return product
            channel = db.query(ProductChannel).filter(ProductChannel.sku == sku).first()
            if channel:
                return db.query(MasterProduct).filter(MasterProduct.master_product_id == channel.master_product_id).first()
        if asin:
            channel = db.query(ProductChannel).filter(ProductChannel.asin == asin).first()
            if channel:
                return db.query(MasterProduct).filter(MasterProduct.master_product_id == channel.master_product_id).first()
        if title:
            product = db.query(MasterProduct).filter(MasterProduct.name == title).first()
            if product:
                return product
        return None

    @staticmethod
    def _resolve_channel(db, master_product_id: str, sku: str | None, asin: str | None, marketplace: str | None):
        q = db.query(ProductChannel).filter(ProductChannel.channel.ilike("%Amazon%"))
        if asin:
            found = q.filter(ProductChannel.asin == asin).first()
            if found:
                return found
        if sku:
            found = q.filter(ProductChannel.sku == sku).first()
            if found:
                return found
        q = db.query(ProductChannel).filter(ProductChannel.master_product_id == master_product_id, ProductChannel.channel.ilike("%Amazon%"))
        if marketplace:
            q = q.filter(ProductChannel.marketplace == marketplace)
        return q.first()

    @staticmethod
    def _new_master_product(sku: str | None, asin: str | None, title: str | None) -> MasterProduct:
        token = sku or asin or uuid4().hex[:8].upper()
        return MasterProduct(
            master_product_id=f"MP-AMZ-{uuid4().hex[:10].upper()}",
            brand=None,
            product_family="Amazon Catalog",
            primary_sku=sku,
            name=title or sku or asin or "Amazon Product",
            status="Active",
            lifecycle_stage="Discovered",
            source="amazon_identity_sync",
            raw={"discovered_from": "seller_central_sales_traffic", "sku": sku, "asin": asin, "token": token},
            active=True,
        )

    @staticmethod
    def _raw(row) -> dict[str, Any]:
        return {
            "source": "seller_central_sales_traffic",
            "title": row.title,
            "country_code": row.country_code,
            "marketplace": row.marketplace,
            "currency": row.currency,
            "last_seen": row.last_seen.isoformat() if row.last_seen else None,
        }

    @staticmethod
    def _clean(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
