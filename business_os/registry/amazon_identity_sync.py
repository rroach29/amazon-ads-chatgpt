"""Amazon Product Identity Sync.

Populates Amazon ProductChannel identity mappings from existing Seller Central
Sales & Traffic rows. This makes ASIN/SKU/marketplace available to Product
Workspace, ChangeSets, and Mission Control without requiring manual entry.

Important model rule:
- A MasterProduct can have multiple Amazon marketplace identities.
- Amazon US and Amazon CA may have different ASINs for the same business product.
- ProductChannel rows are therefore resolved by channel + marketplace + ASIN/SKU,
  not by global ASIN/SKU alone.
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
    version = "business-os-0.7.4-marketplace-identity-preview"

    @classmethod
    def sync_from_seller_central(cls, dry_run: bool = True, limit: int = 1000) -> dict[str, Any]:
        db = SessionLocal()
        try:
            rows = cls._seller_rows(db, limit)
            existing_preview = cls._existing_identity_preview(db, limit=50)

            created_products = 0
            created_channels = 0
            updated_channels = 0
            skipped = 0
            cross_marketplace_links = 0
            samples = []

            for row in rows:
                asin = cls._clean(row.asin)
                sku = cls._clean(row.sku)
                marketplace = cls._marketplace_key(row.country_code or row.marketplace)
                if not asin and not sku:
                    skipped += 1
                    continue

                product = cls._resolve_product(db, sku=sku, asin=asin, title=row.title, marketplace=marketplace)
                product_created = False
                if not product:
                    product_created = True
                    product = cls._new_master_product(sku=sku, asin=asin, title=row.title)
                    if not dry_run:
                        db.add(product)
                        db.flush()
                    created_products += 1

                channel = cls._resolve_channel(db, master_product_id=product.master_product_id, sku=sku, asin=asin, marketplace=marketplace)
                action = "none"
                if not channel:
                    channel = ProductChannel(
                        master_product_id=product.master_product_id,
                        brand=product.brand,
                        primary_sku=product.primary_sku,
                        channel="Amazon",
                        marketplace=marketplace,
                        currency=row.currency,
                        channel_product_id=asin,
                        channel_listing_id=asin,
                        asin=asin,
                        sku=sku,
                        status="Mapped",
                        raw=cls._raw(row, marketplace),
                    )
                    action = "create_marketplace_identity"
                    created_channels += 1
                    if cls._has_other_marketplace_identity(db, product.master_product_id, marketplace):
                        cross_marketplace_links += 1
                    if not dry_run:
                        db.add(channel)
                else:
                    changed = False
                    for attr, value in {
                        "asin": asin,
                        "sku": sku,
                        "channel_product_id": asin,
                        "channel_listing_id": asin,
                        "marketplace": marketplace,
                        "currency": row.currency,
                        "status": "Mapped",
                    }.items():
                        if value and getattr(channel, attr, None) != value:
                            setattr(channel, attr, value)
                            changed = True
                    raw = channel.raw if isinstance(channel.raw, dict) else {}
                    raw.update(cls._raw(row, marketplace))
                    channel.raw = raw
                    if changed:
                        channel.updated_at = datetime.utcnow()
                        updated_channels += 1
                        action = "update_marketplace_identity"

                if len(samples) < 50:
                    samples.append({
                        "action": action,
                        "product_created": product_created,
                        "master_product_id": product.master_product_id,
                        "product_name": product.name,
                        "sku": sku,
                        "asin": asin,
                        "marketplace": marketplace,
                        "last_seen": row.last_seen.isoformat() if row.last_seen else None,
                    })

            if not dry_run:
                db.add(BusinessEvent(
                    event_id=f"EV-{uuid4().hex[:12].upper()}",
                    event_type="AmazonIdentitySync",
                    title="Marketplace-aware Amazon ASIN/SKU identity sync completed",
                    description=f"Created {created_channels} marketplace identities, updated {updated_channels}, created {created_products} products.",
                    source="amazon_identity_sync",
                    payload={
                        "rows_checked": len(rows),
                        "created_products": created_products,
                        "created_channels": created_channels,
                        "updated_channels": updated_channels,
                        "cross_marketplace_links": cross_marketplace_links,
                        "skipped": skipped,
                    },
                ))
                db.commit()

            message = None
            if not rows and existing_preview["existing_marketplace_identities"]:
                message = "No SellerCentralSalesTraffic rows were available to sync, but existing Amazon ProductChannel marketplace identities are already mapped. Showing existing mappings instead."
            elif not rows:
                message = "No SellerCentralSalesTraffic rows were available to sync. Run seller catalog/sales ingestion first, or use existing ProductChannel identities if already mapped."

            return {
                "status": "DRY_RUN" if dry_run else "UPDATED",
                "version": cls.version,
                "source": "seller_central_sales_traffic_plus_existing_product_channels",
                "message": message,
                "model_rule": "One MasterProduct may have separate Amazon marketplace identities, including different US and CA ASINs.",
                "rows_checked": len(rows),
                "created_products": created_products,
                "created_marketplace_identities": created_channels,
                "updated_marketplace_identities": updated_channels,
                "cross_marketplace_links": cross_marketplace_links,
                "skipped": skipped,
                "dry_run": dry_run,
                "sample_mappings": samples,
                **existing_preview,
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
            marketplace_rows = (
                db.query(ProductChannel.marketplace, func.count(ProductChannel.id))
                .filter(ProductChannel.channel.ilike("%Amazon%"))
                .group_by(ProductChannel.marketplace)
                .all()
            )
            multi_marketplace_products = (
                db.query(ProductChannel.master_product_id)
                .filter(ProductChannel.channel.ilike("%Amazon%"))
                .group_by(ProductChannel.master_product_id)
                .having(func.count(func.distinct(ProductChannel.marketplace)) > 1)
                .count()
            )
            return {
                "status": "OK",
                "version": cls.version,
                "model_rule": "ASIN lives on the marketplace identity, not directly on MasterProduct.",
                "amazon_marketplace_identities": total_amazon_channels,
                "amazon_identities_with_asin": mapped_asins,
                "amazon_identities_with_sku": mapped_skus,
                "amazon_identities_by_marketplace": {marketplace or "unknown": count for marketplace, count in marketplace_rows},
                "master_products_with_multiple_amazon_marketplaces": multi_marketplace_products,
                "seller_central_rows": seller_rows,
                "seller_central_distinct_asins": seller_distinct_asins,
                "asin_mapping_pct": round(mapped_asins / total_amazon_channels, 4) if total_amazon_channels else None,
            }
        finally:
            db.close()

    @staticmethod
    def _seller_rows(db, limit: int):
        return (
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

    @staticmethod
    def _existing_identity_preview(db, limit: int = 50) -> dict[str, Any]:
        q = (
            db.query(ProductChannel, MasterProduct)
            .join(MasterProduct, ProductChannel.master_product_id == MasterProduct.master_product_id)
            .filter(ProductChannel.channel.ilike("%Amazon%"))
            .order_by(ProductChannel.marketplace, MasterProduct.name)
            .limit(max(1, min(limit, 500)))
        )
        rows = q.all()
        preview = []
        for channel, product in rows:
            preview.append({
                "action": "existing_marketplace_identity",
                "product_created": False,
                "master_product_id": product.master_product_id,
                "product_name": product.name,
                "sku": channel.sku,
                "asin": channel.asin,
                "marketplace": channel.marketplace,
                "status": channel.status,
                "channel_product_id": channel.channel_product_id,
                "channel_listing_id": channel.channel_listing_id,
            })
        return {
            "existing_marketplace_identities": db.query(ProductChannel).filter(ProductChannel.channel.ilike("%Amazon%")).count(),
            "existing_sample_mappings": preview,
        }

    @staticmethod
    def _resolve_product(db, sku: str | None, asin: str | None, title: str | None, marketplace: str | None):
        if asin:
            channel = AmazonIdentitySyncService._query_amazon_channel(db, marketplace).filter(ProductChannel.asin == asin).first()
            if channel:
                return db.query(MasterProduct).filter(MasterProduct.master_product_id == channel.master_product_id).first()
        if sku:
            channel = AmazonIdentitySyncService._query_amazon_channel(db, marketplace).filter(ProductChannel.sku == sku).first()
            if channel:
                return db.query(MasterProduct).filter(MasterProduct.master_product_id == channel.master_product_id).first()
        if sku:
            product = db.query(MasterProduct).filter(MasterProduct.primary_sku == sku).first()
            if product:
                return product
            any_marketplace_channel = db.query(ProductChannel).filter(ProductChannel.channel.ilike("%Amazon%"), ProductChannel.sku == sku).first()
            if any_marketplace_channel:
                return db.query(MasterProduct).filter(MasterProduct.master_product_id == any_marketplace_channel.master_product_id).first()
        if asin:
            any_asin_channel = db.query(ProductChannel).filter(ProductChannel.channel.ilike("%Amazon%"), ProductChannel.asin == asin).first()
            if any_asin_channel:
                return db.query(MasterProduct).filter(MasterProduct.master_product_id == any_asin_channel.master_product_id).first()
        if title:
            product = db.query(MasterProduct).filter(MasterProduct.name == title).first()
            if product:
                return product
        return None

    @staticmethod
    def _resolve_channel(db, master_product_id: str, sku: str | None, asin: str | None, marketplace: str | None):
        q = AmazonIdentitySyncService._query_amazon_channel(db, marketplace)
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
    def _query_amazon_channel(db, marketplace: str | None):
        q = db.query(ProductChannel).filter(ProductChannel.channel.ilike("%Amazon%"))
        if marketplace:
            q = q.filter(ProductChannel.marketplace == marketplace)
        return q

    @staticmethod
    def _has_other_marketplace_identity(db, master_product_id: str, marketplace: str | None) -> bool:
        q = db.query(ProductChannel).filter(ProductChannel.master_product_id == master_product_id, ProductChannel.channel.ilike("%Amazon%"))
        if marketplace:
            q = q.filter(ProductChannel.marketplace != marketplace)
        return db.query(q.exists()).scalar()

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
    def _raw(row, marketplace: str | None) -> dict[str, Any]:
        return {
            "source": "seller_central_sales_traffic",
            "title": row.title,
            "country_code": row.country_code,
            "marketplace": marketplace,
            "raw_marketplace": row.marketplace,
            "currency": row.currency,
            "last_seen": row.last_seen.isoformat() if row.last_seen else None,
        }

    @staticmethod
    def _marketplace_key(value: Any) -> str | None:
        text = AmazonIdentitySyncService._clean(value)
        if not text:
            return None
        upper = text.upper()
        aliases = {
            "UNITED STATES": "US",
            "USA": "US",
            "US": "US",
            "ATVPDKIKX0DER": "US",
            "CANADA": "CA",
            "CA": "CA",
            "A2EUQ1WTGCTBG2": "CA",
            "AMAZON.COM": "US",
            "AMAZON.CA": "CA",
        }
        return aliases.get(upper, text)

    @staticmethod
    def _clean(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
