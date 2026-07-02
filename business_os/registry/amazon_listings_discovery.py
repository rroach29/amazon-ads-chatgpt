"""Amazon Listings Items discovery for Business OS Registry Intelligence.

Uses the SP-API Listings Items search endpoint as the catalog-first source for
Amazon marketplace identities. This is additive and does not modify the lower
level SPAPIClient; it reuses the existing signed request layer.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote
from uuid import uuid4

from database import SessionLocal
from business_registry.models import MasterProduct, ProductChannel, BusinessEvent
from sp_api import SPAPIClient, SPAPIConfig


class AmazonListingsDiscoveryService:
    version = "business-os-0.8.0-listings-items-discovery"

    @classmethod
    def preview(
        cls,
        marketplace: str = "US",
        page_size: int = 20,
        page_token: str | None = None,
        included_data: str = "summaries,attributes,offers,fulfillmentAvailability,issues",
    ) -> dict[str, Any]:
        client = SPAPIClient(SPAPIConfig.from_env(marketplace))
        response = cls._search(client, marketplace=marketplace, page_size=page_size, page_token=page_token, included_data=included_data)
        if response.get("status") != "OK":
            return response
        listings = cls._normalize_response(response.get("response", {}), marketplace=marketplace)
        return {
            "status": "OK",
            "version": cls.version,
            "marketplace": marketplace,
            "dry_run": True,
            "count": len(listings),
            "next_token": cls._next_token(response.get("response", {})),
            "listings": listings,
            "raw_keys": list((response.get("response") or {}).keys()),
        }

    @classmethod
    def sync(
        cls,
        marketplace: str = "US",
        dry_run: bool = True,
        page_size: int = 20,
        page_token: str | None = None,
        included_data: str = "summaries,attributes,offers,fulfillmentAvailability,issues",
    ) -> dict[str, Any]:
        client = SPAPIClient(SPAPIConfig.from_env(marketplace))
        response = cls._search(client, marketplace=marketplace, page_size=page_size, page_token=page_token, included_data=included_data)
        if response.get("status") != "OK":
            return response
        listings = cls._normalize_response(response.get("response", {}), marketplace=marketplace)

        db = SessionLocal()
        try:
            created_products = 0
            created_identities = 0
            updated_identities = 0
            samples = []
            for listing in listings:
                product = cls._resolve_product(db, listing)
                product_created = False
                if not product:
                    product_created = True
                    product = cls._new_product(listing)
                    created_products += 1
                    if not dry_run:
                        db.add(product)
                        db.flush()

                channel = cls._resolve_channel(db, product.master_product_id, listing)
                action = "none"
                if not channel:
                    action = "create_marketplace_identity"
                    created_identities += 1
                    if not dry_run:
                        db.add(cls._new_channel(product, listing))
                else:
                    changes = cls._apply_channel_updates(channel, listing)
                    if changes:
                        action = "update_marketplace_identity"
                        updated_identities += 1

                if len(samples) < 50:
                    samples.append({**listing, "action": action, "product_created": product_created, "master_product_id": product.master_product_id, "product_name": product.name})

            if not dry_run:
                db.add(BusinessEvent(
                    event_id=f"EV-{uuid4().hex[:12].upper()}",
                    event_type="AmazonListingsDiscovery",
                    title="Amazon Listings Items discovery sync completed",
                    description=f"Marketplace {marketplace}: created {created_identities}, updated {updated_identities}, created products {created_products}.",
                    source="amazon_listings_discovery",
                    payload={"marketplace": marketplace, "created_products": created_products, "created_identities": created_identities, "updated_identities": updated_identities, "count": len(listings)},
                ))
                db.commit()

            return {
                "status": "DRY_RUN" if dry_run else "UPDATED",
                "version": cls.version,
                "marketplace": marketplace,
                "dry_run": dry_run,
                "count": len(listings),
                "next_token": cls._next_token(response.get("response", {})),
                "created_products": created_products,
                "created_marketplace_identities": created_identities,
                "updated_marketplace_identities": updated_identities,
                "sample_mappings": samples,
            }
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def _search(client: SPAPIClient, marketplace: str, page_size: int, page_token: str | None, included_data: str) -> dict[str, Any]:
        seller_id = client.config.seller_id
        if not seller_id:
            return {"status": "ERROR", "message": "Seller ID is required.", "hint": "Set SP_API_SELLER_ID or AMAZON_SELLER_ID."}
        marketplace_id = client._resolve_marketplace_id(client.config.marketplace_id or marketplace)
        query: dict[str, Any] = {
            "marketplaceIds": [marketplace_id],
            "includedData": included_data,
            "pageSize": max(1, min(int(page_size or 20), 20)),
        }
        if page_token:
            query["pageToken"] = page_token
        return client._request("GET", f"/listings/2021-08-01/items/{quote(seller_id, safe='')}", query=query)

    @staticmethod
    def _normalize_response(payload: dict[str, Any], marketplace: str) -> list[dict[str, Any]]:
        items = payload.get("items") or payload.get("listings") or []
        output = []
        for item in items:
            summaries = item.get("summaries") or []
            summary = summaries[0] if summaries else {}
            sku = item.get("sku") or item.get("sellerSku") or summary.get("sellerSku")
            asin = item.get("asin") or summary.get("asin")
            title = summary.get("itemName") or summary.get("title") or item.get("title")
            status = summary.get("status") or item.get("status")
            product_type = summary.get("productType") or item.get("productType")
            output.append({
                "marketplace": marketplace,
                "marketplace_id": summary.get("marketplaceId") or item.get("marketplaceId"),
                "sku": sku,
                "asin": asin,
                "title": title,
                "status": status,
                "product_type": product_type,
                "raw": item,
            })
        return output

    @staticmethod
    def _next_token(payload: dict[str, Any]) -> str | None:
        pagination = payload.get("pagination") or {}
        return pagination.get("nextToken") or payload.get("nextToken")

    @staticmethod
    def _resolve_product(db, listing: dict[str, Any]):
        asin = listing.get("asin")
        sku = listing.get("sku")
        marketplace = listing.get("marketplace")
        if asin:
            channel = db.query(ProductChannel).filter(ProductChannel.channel.ilike("%Amazon%"), ProductChannel.marketplace == marketplace, ProductChannel.asin == asin).first()
            if channel:
                return db.query(MasterProduct).filter(MasterProduct.master_product_id == channel.master_product_id).first()
        if sku:
            channel = db.query(ProductChannel).filter(ProductChannel.channel.ilike("%Amazon%"), ProductChannel.marketplace == marketplace, ProductChannel.sku == sku).first()
            if channel:
                return db.query(MasterProduct).filter(MasterProduct.master_product_id == channel.master_product_id).first()
            product = db.query(MasterProduct).filter(MasterProduct.primary_sku == sku).first()
            if product:
                return product
        title = listing.get("title")
        if title:
            return db.query(MasterProduct).filter(MasterProduct.name == title).first()
        return None

    @staticmethod
    def _resolve_channel(db, master_product_id: str, listing: dict[str, Any]):
        marketplace = listing.get("marketplace")
        asin = listing.get("asin")
        sku = listing.get("sku")
        q = db.query(ProductChannel).filter(ProductChannel.channel.ilike("%Amazon%"), ProductChannel.marketplace == marketplace)
        if asin:
            found = q.filter(ProductChannel.asin == asin).first()
            if found:
                return found
        if sku:
            found = q.filter(ProductChannel.sku == sku).first()
            if found:
                return found
        return db.query(ProductChannel).filter(ProductChannel.master_product_id == master_product_id, ProductChannel.channel.ilike("%Amazon%"), ProductChannel.marketplace == marketplace).first()

    @staticmethod
    def _new_product(listing: dict[str, Any]) -> MasterProduct:
        return MasterProduct(
            master_product_id=f"MP-AMZ-{uuid4().hex[:10].upper()}",
            product_family="Amazon Catalog",
            primary_sku=listing.get("sku"),
            name=listing.get("title") or listing.get("sku") or listing.get("asin") or "Amazon Listing",
            status="Active",
            lifecycle_stage="Discovered",
            source="amazon_listings_discovery",
            raw={"source": "listings_items_api", "asin": listing.get("asin"), "sku": listing.get("sku"), "marketplace": listing.get("marketplace")},
            active=True,
        )

    @staticmethod
    def _new_channel(product: MasterProduct, listing: dict[str, Any]) -> ProductChannel:
        return ProductChannel(
            master_product_id=product.master_product_id,
            brand=product.brand,
            primary_sku=product.primary_sku,
            channel="Amazon",
            marketplace=listing.get("marketplace"),
            channel_product_id=listing.get("asin"),
            channel_listing_id=listing.get("asin"),
            asin=listing.get("asin"),
            sku=listing.get("sku"),
            status=listing.get("status") or "Discovered",
            raw={"source": "listings_items_api", "listing": listing},
        )

    @staticmethod
    def _apply_channel_updates(channel: ProductChannel, listing: dict[str, Any]) -> list[str]:
        changes = []
        for attr, value in {
            "asin": listing.get("asin"),
            "sku": listing.get("sku"),
            "channel_product_id": listing.get("asin"),
            "channel_listing_id": listing.get("asin"),
            "status": listing.get("status") or "Discovered",
        }.items():
            if value and getattr(channel, attr, None) != value:
                setattr(channel, attr, value)
                changes.append(attr)
        raw = channel.raw if isinstance(channel.raw, dict) else {}
        raw["listings_items_api"] = listing
        channel.raw = raw
        return changes
