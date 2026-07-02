"""Legacy Master Product ID audit.

Read-only audit for source-encoded IDs such as MP-AMZ-*.
"""

from __future__ import annotations

from typing import Any

from database import SessionLocal
from business_registry.models import MasterProduct, ProductChannel
from business_os.registry.master_product_ids import MasterProductIdService


class LegacyIdAuditService:
    version = "business-os-1.0.0-legacy-id-audit"

    @classmethod
    def audit(cls, limit: int = 500) -> dict[str, Any]:
        db = SessionLocal()
        try:
            products = db.query(MasterProduct).filter(MasterProduct.master_product_id.like("MP-AMZ-%")).order_by(MasterProduct.name.asc()).limit(limit).all()
            rows = []
            for product in products:
                channels = db.query(ProductChannel).filter(ProductChannel.master_product_id == product.master_product_id).all()
                raw = product.raw if isinstance(product.raw, dict) else {}
                rows.append({
                    "master_product_id": product.master_product_id,
                    "name": product.name,
                    "brand": product.brand,
                    "product_family": product.product_family,
                    "primary_sku": product.primary_sku,
                    "status": product.status,
                    "lifecycle_stage": product.lifecycle_stage,
                    "source": product.source,
                    "created_source": raw.get("created_source") or raw.get("source"),
                    "source_identifier": raw.get("source_identifier") or raw.get("asin") or raw.get("sku"),
                    "marketplace": raw.get("marketplace"),
                    "asin": raw.get("asin"),
                    "sku": raw.get("sku"),
                    "channel_count": len(channels),
                    "channels": [{"channel": c.channel, "marketplace": c.marketplace, "asin": c.asin, "sku": c.sku, "status": c.status} for c in channels],
                    "recommendation": cls._recommendation(product, channels),
                })
            return {
                "status": "OK",
                "version": cls.version,
                "legacy_id_count": len(rows),
                "id_policy": "Master Product IDs should be marketplace-neutral sequential IDs. Legacy MP-AMZ-* IDs are preserved until explicitly renumbered or merged.",
                "rows": rows,
            }
        finally:
            db.close()

    @staticmethod
    def _recommendation(product: MasterProduct, channels: list[ProductChannel]) -> str:
        if not channels:
            return "REVIEW_OR_ARCHIVE"
        if len(channels) == 1:
            return "RENUMBER_CANDIDATE"
        return "REVIEW_MULTI_CHANNEL_BEFORE_RENUMBER"
