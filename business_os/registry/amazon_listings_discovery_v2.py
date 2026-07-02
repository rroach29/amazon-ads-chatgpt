"""Sequential-ID wrapper for Amazon Listings discovery.

Prevents new Amazon-discovered Master Products from receiving source-encoded IDs
like MP-AMZ-*. Source details are stored in raw metadata instead.
"""

from __future__ import annotations

from database import SessionLocal
from business_registry.models import MasterProduct
from business_os.registry.amazon_listings_discovery import AmazonListingsDiscoveryService as _BaseAmazonListingsDiscoveryService
from business_os.registry.master_product_ids import MasterProductIdService


class AmazonListingsDiscoveryService(_BaseAmazonListingsDiscoveryService):
    version = "business-os-1.0.1-sequential-master-product-ids"

    @staticmethod
    def _new_product(listing: dict) -> MasterProduct:
        db = SessionLocal()
        try:
            master_product_id = MasterProductIdService.next_id(db)
        finally:
            db.close()
        return MasterProduct(
            master_product_id=master_product_id,
            brand=listing.get("brand"),
            product_family=listing.get("product_type") or "Amazon Catalog",
            primary_sku=listing.get("parent_sku") or listing.get("sku"),
            name=listing.get("title") or listing.get("sku") or listing.get("asin") or "Amazon Listing",
            status="Active",
            lifecycle_stage="Discovered",
            source="amazon_listings_discovery",
            raw={
                "source": "listings_items_api",
                "created_by": "Amazon Sync",
                "created_source": f"Amazon {listing.get('marketplace')}",
                "source_identifier": listing.get("asin") or listing.get("sku"),
                "id_policy": "sequential_marketplace_neutral",
                "asin": listing.get("asin"),
                "sku": listing.get("sku"),
                "marketplace": listing.get("marketplace"),
                "parent_sku": listing.get("parent_sku"),
            },
            active=True,
        )
