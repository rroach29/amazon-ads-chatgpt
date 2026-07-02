"""Amazon Listings Items discovery for Business OS Registry Intelligence.

Uses SP-API Listings Items as the catalog-first Amazon source, but all writes
must pass through a registry gatekeeper. The gatekeeper prevents silent Master
Product drift by only auto-creating new Master Products when explicitly allowed.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from database import SessionLocal
from business_registry.models import MasterProduct, ProductChannel, BusinessEvent
from sp_api import SPAPIClient, SPAPIConfig


class AmazonListingsDiscoveryService:
    version = "business-os-0.8.2-registry-gatekeeper"

    @classmethod
    def preview(cls, marketplace: str = "US", page_size: int = 20, page_token: str | None = None, included_data: str = "summaries,attributes,offers,fulfillmentAvailability,issues") -> dict[str, Any]:
        client = SPAPIClient(SPAPIConfig.from_env(marketplace))
        response = cls._search(client, marketplace=marketplace, page_size=page_size, page_token=page_token, included_data=included_data)
        if response.get("status") != "OK":
            return response
        listings = cls._normalize_response(response.get("response", {}), marketplace=marketplace)
        return {"status": "OK", "version": cls.version, "marketplace": marketplace, "dry_run": True, "count": len(listings), "next_token": cls._next_token(response.get("response", {})), "listings": listings, "raw_keys": list((response.get("response") or {}).keys())}

    @classmethod
    def sync(cls, marketplace: str = "US", dry_run: bool = True, page_size: int = 20, page_token: str | None = None, included_data: str = "summaries,attributes,offers,fulfillmentAvailability,issues", create_missing_products: bool = False) -> dict[str, Any]:
        client = SPAPIClient(SPAPIConfig.from_env(marketplace))
        response = cls._search(client, marketplace=marketplace, page_size=page_size, page_token=page_token, included_data=included_data)
        if response.get("status") != "OK":
            return response
        listings = cls._normalize_response(response.get("response", {}), marketplace=marketplace)
        return cls._sync_listings(listings=listings, marketplace=marketplace, dry_run=dry_run, next_token=cls._next_token(response.get("response", {})), create_missing_products=create_missing_products)

    @classmethod
    def sync_all(cls, marketplace: str = "US", dry_run: bool = True, page_size: int = 20, max_pages: int = 10, included_data: str = "summaries,attributes,offers,fulfillmentAvailability,issues", create_missing_products: bool = False) -> dict[str, Any]:
        client = SPAPIClient(SPAPIConfig.from_env(marketplace))
        all_listings: list[dict[str, Any]] = []
        token = None
        pages = 0
        while pages < max(1, min(max_pages, 50)):
            response = cls._search(client, marketplace=marketplace, page_size=page_size, page_token=token, included_data=included_data)
            if response.get("status") != "OK":
                return {**response, "version": cls.version, "marketplace": marketplace, "pages_completed": pages, "listings_collected": len(all_listings)}
            payload = response.get("response", {})
            all_listings.extend(cls._normalize_response(payload, marketplace=marketplace))
            pages += 1
            token = cls._next_token(payload)
            if not token:
                break
        result = cls._sync_listings(listings=all_listings, marketplace=marketplace, dry_run=dry_run, next_token=token, create_missing_products=create_missing_products)
        result["pages_processed"] = pages
        result["has_more"] = bool(token)
        return result

    @classmethod
    def _sync_listings(cls, listings: list[dict[str, Any]], marketplace: str, dry_run: bool, next_token: str | None, create_missing_products: bool = False) -> dict[str, Any]:
        db = SessionLocal()
        try:
            created_products = 0
            created_identities = 0
            updated_identities = 0
            auto_matched_products = 0
            review_needed = 0
            blocked_new_products = 0
            samples = []
            review_queue = []

            for listing in listings:
                match = cls._match_product(db, listing)
                product = match.get("product")
                product_created = False
                gated = False

                if not product:
                    if create_missing_products:
                        product_created = True
                        product = cls._new_product(listing)
                        created_products += 1
                        if not dry_run:
                            db.add(product)
                            db.flush()
                    else:
                        gated = True
                        blocked_new_products += 1
                        review_needed += 1
                        review_row = cls._review_row(listing, match, reason="no confident master product match; creation blocked by registry gatekeeper")
                        review_queue.append(review_row)
                        if len(samples) < 75:
                            samples.append(review_row)
                        continue
                else:
                    if match.get("confidence", 0) >= 95:
                        auto_matched_products += 1
                    else:
                        review_needed += 1
                        review_queue.append(cls._review_row(listing, match, product=product, reason="matched below auto-link confidence threshold"))

                channel = cls._resolve_channel(db, product.master_product_id, listing)
                action = "none"
                if not channel:
                    action = "create_marketplace_identity"
                    created_identities += 1
                    if not dry_run:
                        db.add(cls._new_channel(product, listing, match))
                else:
                    changes = cls._apply_channel_updates(channel, listing, match)
                    if changes:
                        action = "update_marketplace_identity"
                        updated_identities += 1

                if len(samples) < 75:
                    samples.append({**listing, "action": action, "product_created": product_created, "creation_blocked": gated, "master_product_id": product.master_product_id, "product_name": product.name, "match_confidence": match.get("confidence", 0), "match_reason": match.get("reason"), "needs_review": match.get("confidence", 0) < 95 and not product_created})

            if not dry_run:
                db.add(BusinessEvent(event_id=f"EV-{uuid4().hex[:12].upper()}", event_type="AmazonListingsDiscovery", title="Amazon Listings Items discovery sync completed", description=f"Marketplace {marketplace}: created identities {created_identities}, updated {updated_identities}, created products {created_products}, blocked new products {blocked_new_products}.", source="amazon_listings_discovery", payload={"marketplace": marketplace, "created_products": created_products, "created_identities": created_identities, "updated_identities": updated_identities, "auto_matched_products": auto_matched_products, "review_needed": review_needed, "blocked_new_products": blocked_new_products, "create_missing_products": create_missing_products, "count": len(listings), "review_queue_sample": review_queue[:50]}))
                db.commit()

            return {"status": "DRY_RUN" if dry_run else "UPDATED", "version": cls.version, "marketplace": marketplace, "dry_run": dry_run, "registry_gatekeeper": {"create_missing_products": create_missing_products, "rule": "New Master Products are blocked unless create_missing_products=true."}, "count": len(listings), "next_token": next_token, "created_products": created_products, "created_marketplace_identities": created_identities, "updated_marketplace_identities": updated_identities, "auto_matched_products": auto_matched_products, "review_needed": review_needed, "blocked_new_products": blocked_new_products, "sample_mappings": samples, "review_queue": review_queue[:100]}
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def _review_row(listing: dict[str, Any], match: dict[str, Any], product: MasterProduct | None = None, reason: str | None = None) -> dict[str, Any]:
        return {**listing, "action": "registry_review_required", "creation_blocked": product is None, "master_product_id": product.master_product_id if product else None, "product_name": product.name if product else None, "match_confidence": match.get("confidence", 0), "match_reason": match.get("reason"), "needs_review": True, "review_reason": reason}

    @staticmethod
    def _search(client: SPAPIClient, marketplace: str, page_size: int, page_token: str | None, included_data: str) -> dict[str, Any]:
        seller_id = client.config.seller_id
        if not seller_id:
            return {"status": "ERROR", "message": "Seller ID is required.", "hint": "Set SP_API_SELLER_ID or AMAZON_SELLER_ID."}
        marketplace_id = client._resolve_marketplace_id(client.config.marketplace_id or marketplace)
        query: dict[str, Any] = {"marketplaceIds": [marketplace_id], "includedData": included_data, "pageSize": max(1, min(int(page_size or 20), 20))}
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
            attributes = item.get("attributes") or {}
            sku = item.get("sku") or item.get("sellerSku") or summary.get("sellerSku")
            asin = item.get("asin") or summary.get("asin") or AmazonListingsDiscoveryService._attr_value(attributes, "merchant_suggested_asin")
            title = summary.get("itemName") or summary.get("title") or item.get("title") or AmazonListingsDiscoveryService._attr_value(attributes, "item_name")
            status = summary.get("status") or item.get("status")
            product_type = summary.get("productType") or item.get("productType")
            parent_sku = AmazonListingsDiscoveryService._relationship_parent_sku(attributes)
            parentage = AmazonListingsDiscoveryService._attr_value(attributes, "parentage_level")
            brand = AmazonListingsDiscoveryService._attr_value(attributes, "brand") or AmazonListingsDiscoveryService._attr_value(attributes, "manufacturer")
            output.append({"marketplace": marketplace, "marketplace_id": summary.get("marketplaceId") or item.get("marketplaceId"), "sku": sku, "asin": asin, "title": title, "brand": brand, "status": status, "product_type": product_type, "parent_sku": parent_sku, "parentage": parentage, "raw": item})
        return output

    @staticmethod
    def _next_token(payload: dict[str, Any]) -> str | None:
        pagination = payload.get("pagination") or {}
        return pagination.get("nextToken") or payload.get("nextToken")

    @staticmethod
    def _match_product(db, listing: dict[str, Any]) -> dict[str, Any]:
        asin = listing.get("asin")
        sku = listing.get("sku")
        parent_sku = listing.get("parent_sku")
        title = listing.get("title")
        marketplace = listing.get("marketplace")
        if asin:
            channel = db.query(ProductChannel).filter(ProductChannel.channel.ilike("%Amazon%"), ProductChannel.marketplace == marketplace, ProductChannel.asin == asin).first()
            if channel:
                product = db.query(MasterProduct).filter(MasterProduct.master_product_id == channel.master_product_id).first()
                if product:
                    return {"product": product, "confidence": 100, "reason": "same marketplace ASIN"}
        if sku:
            channel = db.query(ProductChannel).filter(ProductChannel.channel.ilike("%Amazon%"), ProductChannel.marketplace == marketplace, ProductChannel.sku == sku).first()
            if channel:
                product = db.query(MasterProduct).filter(MasterProduct.master_product_id == channel.master_product_id).first()
                if product:
                    return {"product": product, "confidence": 100, "reason": "same marketplace SKU"}
            product = db.query(MasterProduct).filter(MasterProduct.primary_sku == sku).first()
            if product:
                return {"product": product, "confidence": 98, "reason": "primary SKU"}
        if parent_sku:
            channel = db.query(ProductChannel).filter(ProductChannel.channel.ilike("%Amazon%"), ProductChannel.sku == parent_sku).first()
            if channel:
                product = db.query(MasterProduct).filter(MasterProduct.master_product_id == channel.master_product_id).first()
                if product:
                    return {"product": product, "confidence": 92, "reason": "variation parent SKU; review family relationship"}
            product = db.query(MasterProduct).filter(MasterProduct.primary_sku == parent_sku).first()
            if product:
                return {"product": product, "confidence": 92, "reason": "primary parent SKU; review family relationship"}
        if title:
            exact = db.query(MasterProduct).filter(MasterProduct.name == title).first()
            if exact:
                return {"product": exact, "confidence": 95, "reason": "exact title"}
            candidates = db.query(MasterProduct).limit(500).all()
            best = None
            best_score = 0.0
            normalized = AmazonListingsDiscoveryService._normalize_title(title)
            for candidate in candidates:
                score = SequenceMatcher(None, normalized, AmazonListingsDiscoveryService._normalize_title(candidate.name or "")).ratio()
                if score > best_score:
                    best_score = score
                    best = candidate
            if best and best_score >= 0.88:
                return {"product": best, "confidence": min(round(best_score * 100), 94), "reason": "normalized title similarity; review before linking"}
        return {"product": None, "confidence": 0, "reason": "new or unmatched listing"}

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
        return MasterProduct(master_product_id=f"MP-AMZ-{uuid4().hex[:10].upper()}", brand=listing.get("brand"), product_family=listing.get("product_type") or "Amazon Catalog", primary_sku=listing.get("parent_sku") or listing.get("sku"), name=listing.get("title") or listing.get("sku") or listing.get("asin") or "Amazon Listing", status="Active", lifecycle_stage="Discovered", source="amazon_listings_discovery", raw={"source": "listings_items_api", "asin": listing.get("asin"), "sku": listing.get("sku"), "marketplace": listing.get("marketplace"), "parent_sku": listing.get("parent_sku")}, active=True)

    @staticmethod
    def _new_channel(product: MasterProduct, listing: dict[str, Any], match: dict[str, Any] | None = None) -> ProductChannel:
        return ProductChannel(master_product_id=product.master_product_id, brand=listing.get("brand") or product.brand, primary_sku=product.primary_sku, channel="Amazon", marketplace=listing.get("marketplace"), channel_product_id=listing.get("asin"), channel_listing_id=listing.get("asin"), asin=listing.get("asin"), sku=listing.get("sku"), status=listing.get("status") or "Discovered", raw={"source": "listings_items_api", "listing": listing, "match": {"confidence": (match or {}).get("confidence"), "reason": (match or {}).get("reason")}})

    @staticmethod
    def _apply_channel_updates(channel: ProductChannel, listing: dict[str, Any], match: dict[str, Any] | None = None) -> list[str]:
        changes = []
        for attr, value in {"asin": listing.get("asin"), "sku": listing.get("sku"), "channel_product_id": listing.get("asin"), "channel_listing_id": listing.get("asin"), "status": listing.get("status") or "Discovered"}.items():
            if value and getattr(channel, attr, None) != value:
                setattr(channel, attr, value)
                changes.append(attr)
        raw = channel.raw if isinstance(channel.raw, dict) else {}
        raw["listings_items_api"] = listing
        raw["match"] = {"confidence": (match or {}).get("confidence"), "reason": (match or {}).get("reason")}
        channel.raw = raw
        return changes

    @staticmethod
    def _attr_value(attributes: dict[str, Any], key: str) -> Any:
        values = attributes.get(key) or []
        if not values:
            return None
        first = values[0]
        if isinstance(first, dict):
            return first.get("value")
        return first

    @staticmethod
    def _relationship_parent_sku(attributes: dict[str, Any]) -> str | None:
        relationships = attributes.get("child_parent_sku_relationship") or []
        for row in relationships:
            if isinstance(row, dict) and row.get("parent_sku"):
                return row.get("parent_sku")
        return None

    @staticmethod
    def _normalize_title(text: str) -> str:
        text = str(text or "").lower()
        text = re.sub(r"\([^)]*\)", " ", text)
        text = re.sub(r"[^a-z0-9]+", " ", text)
        stop = {"the", "and", "with", "for", "gift", "gifts", "unique", "style", "medium", "large", "small", "brown", "black", "white", "blue", "red"}
        return " ".join([word for word in text.split() if word not in stop])
