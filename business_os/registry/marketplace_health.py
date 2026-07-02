"""Marketplace Registry Health.

General marketplace identity health across Amazon, Etsy, Shopify, eBay,
Meta, Google, and future channels. This is intentionally read-only.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func

from database import SessionLocal
from business_registry.models import MasterProduct, ProductChannel


class MarketplaceRegistryHealthService:
    version = "business-os-0.7.5-marketplace-registry-health"
    expected_channels = ["Amazon", "Etsy", "Shopify", "eBay", "Meta", "Google"]

    @classmethod
    def summary(cls) -> dict[str, Any]:
        db = SessionLocal()
        try:
            total_products = db.query(MasterProduct).filter(MasterProduct.active == True).count()
            total_identities = db.query(ProductChannel).count()
            channel_rows = (
                db.query(ProductChannel.channel, func.count(ProductChannel.id))
                .group_by(ProductChannel.channel)
                .all()
            )
            marketplace_rows = (
                db.query(ProductChannel.channel, ProductChannel.marketplace, func.count(ProductChannel.id))
                .group_by(ProductChannel.channel, ProductChannel.marketplace)
                .all()
            )

            channels = []
            all_channel_names = sorted(set(cls.expected_channels + [row[0] for row in channel_rows if row[0]]))
            for channel in all_channel_names:
                channels.append(cls._channel_health(db, channel))

            products_with_any_identity = (
                db.query(ProductChannel.master_product_id)
                .distinct()
                .count()
            )
            products_without_identity = max(total_products - products_with_any_identity, 0)
            multi_channel_products = (
                db.query(ProductChannel.master_product_id)
                .group_by(ProductChannel.master_product_id)
                .having(func.count(func.distinct(ProductChannel.channel)) > 1)
                .count()
            )
            multi_marketplace_products = (
                db.query(ProductChannel.master_product_id)
                .group_by(ProductChannel.master_product_id)
                .having(func.count(func.distinct(ProductChannel.marketplace)) > 1)
                .count()
            )

            completeness = cls._overall_completeness(total_products, total_identities, channels)

            return {
                "status": "OK",
                "version": cls.version,
                "summary": {
                    "master_products": total_products,
                    "marketplace_identities": total_identities,
                    "products_with_any_identity": products_with_any_identity,
                    "products_without_identity": products_without_identity,
                    "multi_channel_products": multi_channel_products,
                    "multi_marketplace_products": multi_marketplace_products,
                    "overall_completeness_pct": completeness,
                },
                "channels": channels,
                "identities_by_channel": {channel or "unknown": count for channel, count in channel_rows},
                "identities_by_channel_marketplace": [
                    {"channel": channel or "unknown", "marketplace": marketplace or "unknown", "count": count}
                    for channel, marketplace, count in marketplace_rows
                ],
                "notes": [
                    "Marketplace identity is the channel-specific listing/product record under a MasterProduct.",
                    "Amazon US and Amazon CA may be separate identities with different ASINs.",
                    "eBay should be modeled as its own marketplace identity with listing ID, SKU, site, status, price, quantity, and URL.",
                ],
            }
        finally:
            db.close()

    @classmethod
    def _channel_health(cls, db, channel: str) -> dict[str, Any]:
        q = db.query(ProductChannel).filter(ProductChannel.channel.ilike(f"%{channel}%"))
        count = q.count()
        with_sku = q.filter(ProductChannel.sku.isnot(None)).count()
        with_asin = q.filter(ProductChannel.asin.isnot(None)).count()
        with_listing_id = q.filter(
            (ProductChannel.channel_listing_id.isnot(None)) | (ProductChannel.listing_id.isnot(None))
            if hasattr(ProductChannel, "listing_id") else ProductChannel.channel_listing_id.isnot(None)
        ).count()
        marketplaces = [row[0] for row in q.with_entities(ProductChannel.marketplace).distinct().all() if row[0]]

        required = cls._required_fields(channel)
        filled_scores = []
        if "sku" in required:
            filled_scores.append(with_sku / count if count else 0)
        if "asin" in required:
            filled_scores.append(with_asin / count if count else 0)
        if "listing_id" in required:
            filled_scores.append(with_listing_id / count if count else 0)
        completeness = round((sum(filled_scores) / len(filled_scores)) * 100) if filled_scores else (100 if count else 0)

        return {
            "channel": channel,
            "identity_count": count,
            "marketplaces": sorted(marketplaces),
            "with_sku": with_sku,
            "with_asin": with_asin,
            "with_listing_id": with_listing_id,
            "required_fields": required,
            "completeness_pct": completeness,
            "status": "mapped" if count else "not_connected_yet",
        }

    @staticmethod
    def _required_fields(channel: str) -> list[str]:
        key = channel.lower()
        if "amazon" in key:
            return ["sku", "asin"]
        if "etsy" in key:
            return ["listing_id", "sku"]
        if "shopify" in key:
            return ["listing_id", "sku"]
        if "ebay" in key:
            return ["listing_id", "sku"]
        if "meta" in key or "google" in key:
            return ["listing_id", "sku"]
        return ["listing_id", "sku"]

    @staticmethod
    def _overall_completeness(total_products: int, total_identities: int, channels: list[dict[str, Any]]) -> int:
        if not total_products and not total_identities:
            return 0
        identity_coverage = min(100, round((total_identities / total_products) * 100)) if total_products else 0
        mapped_channels = [c for c in channels if c.get("identity_count", 0) > 0]
        avg_channel = round(sum(c.get("completeness_pct", 0) for c in mapped_channels) / len(mapped_channels)) if mapped_channels else 0
        return round((identity_coverage * 0.5) + (avg_channel * 0.5))
