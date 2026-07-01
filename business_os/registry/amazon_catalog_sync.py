"""Amazon Catalog/Listings Identity Sync.

Uses SP-API Listings Items API as the authoritative SKU -> ASIN source.
This complements Sales & Traffic, which may contain SKU but not ASIN.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from database import SessionLocal
from models import SellerCentralSalesTraffic
from business_registry.models import MasterProduct, ProductChannel, BusinessEvent
from sp_api import SPAPIClient, SPAPIConfig


class AmazonCatalogSyncService:
    version = "business-os-0.7.2-amazon-catalog-sync"

    @classmethod
    def sync_skus(
        cls,
        marketplace: str = "US",
        marketplace_id: str | None = None,
        seller_id: str | None = None,
        dry_run: bool = True,
        limit: int = 50,
    ) -> dict[str, Any]:
        db = SessionLocal()
        try:
            client = SPAPIClient(SPAPIConfig.from_env(marketplace))
            marketplace_id = marketplace_id or client.config.marketplace_id
            skus = cls._candidate_skus(db, marketplace=marketplace, limit=limit)

            checked = 0
            resolved = 0
            updated_channels = 0
            created_channels = 0
            errors = []
            samples = []

            for sku in skus:
                checked += 1
                response = client.get_listings_item(
                    sku=sku,
                    marketplace_id=marketplace_id,
                    seller_id=seller_id,
                )
                if response.get("status") != "OK":
                    errors.append({"sku": sku, "status": response.get("status"), "message": response.get("message"), "http_status": response.get("http_status")})
                    if len(errors) >= 10:
                        break
                    continue

                payload = response.get("response") or {}
                listing = cls._parse_listing_payload(payload, sku=sku, marketplace=marketplace, marketplace_id=marketplace_id)
                if not listing.get("asin"):
                    errors.append({"sku": sku, "status": "NO_ASIN", "message": "Listings API response did not include an ASIN.", "response_keys": list(payload.keys())})
                    continue

                resolved += 1
                product = cls._resolve_or_build_product(db, listing, dry_run=dry_run)
                action = cls._upsert_channel(db, product, listing, dry_run=dry_run)
                if action == "created":
                    created_channels += 1
                elif action == "updated":
                    updated_channels += 1

                if len(samples) < 50:
                    samples.append({
                        "sku": sku,
                        "asin": listing.get("asin"),
                        "title": listing.get("title"),
                        "status": listing.get("status"),
                        "marketplace": marketplace,
                        "master_product_id": product.master_product_id,
                        "action": action,
                    })

            if not dry_run:
                db.add(BusinessEvent(
                    event_id=f"EV-{uuid4().hex[:12].upper()}",
                    event_type="AmazonCatalogSync",
                    title="Amazon Listings ASIN sync completed",
                    description=f"Resolved {resolved} Amazon listings from {checked} SKU checks.",
                    source="amazon_catalog_sync",
                    payload={
                        "marketplace": marketplace,
                        "marketplace_id": marketplace_id,
                        "checked": checked,
                        "resolved": resolved,
                        "created_channels": created_channels,
                        "updated_channels": updated_channels,
                        "error_count": len(errors),
                    },
                ))
                db.commit()

            return {
                "status": "DRY_RUN" if dry_run else "UPDATED",
                "version": cls.version,
                "marketplace": marketplace,
                "marketplace_id": marketplace_id,
                "checked": checked,
                "candidate_skus": len(skus),
                "resolved_asins": resolved,
                "created_channels": created_channels,
                "updated_channels": updated_channels,
                "dry_run": dry_run,
                "sample_mappings": samples,
                "errors": errors,
                "next_step": "If dry_run looks good, rerun with dry_run=false. If errors mention Seller ID, set SP_API_SELLER_ID or pass seller_id.",
            }
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc), "dry_run": dry_run}
        finally:
            db.close()

    @classmethod
    def lookup_sku(
        cls,
        sku: str,
        marketplace: str = "US",
        marketplace_id: str | None = None,
        seller_id: str | None = None,
    ) -> dict[str, Any]:
        client = SPAPIClient(SPAPIConfig.from_env(marketplace))
        response = client.get_listings_item(sku=sku, marketplace_id=marketplace_id or client.config.marketplace_id, seller_id=seller_id)
        if response.get("status") != "OK":
            return response
        return {
            "status": "OK",
            "version": cls.version,
            "listing": cls._parse_listing_payload(response.get("response") or {}, sku=sku, marketplace=marketplace, marketplace_id=marketplace_id or client.config.marketplace_id),
            "raw": response.get("response"),
        }

    @staticmethod
    def _candidate_skus(db, marketplace: str, limit: int) -> list[str]:
        candidates: list[str] = []
        seen = set()

        channel_rows = (
            db.query(ProductChannel.sku)
            .filter(ProductChannel.channel.ilike("%Amazon%"), ProductChannel.sku.isnot(None))
            .limit(max(1, min(limit * 2, 10000)))
            .all()
        )
        for row in channel_rows:
            sku = AmazonCatalogSyncService._clean(row[0])
            if sku and sku not in seen:
                seen.add(sku)
                candidates.append(sku)
            if len(candidates) >= limit:
                return candidates

        seller_rows = (
            db.query(SellerCentralSalesTraffic.sku)
            .filter(SellerCentralSalesTraffic.sku.isnot(None))
            .limit(max(1, min(limit * 3, 10000)))
            .all()
        )
        for row in seller_rows:
            sku = AmazonCatalogSyncService._clean(row[0])
            if sku and sku not in seen:
                seen.add(sku)
                candidates.append(sku)
            if len(candidates) >= limit:
                break
        return candidates

    @staticmethod
    def _parse_listing_payload(payload: dict[str, Any], sku: str, marketplace: str, marketplace_id: str | None) -> dict[str, Any]:
        summaries = payload.get("summaries") or []
        summary = summaries[0] if summaries and isinstance(summaries[0], dict) else {}
        attributes = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {}
        title = summary.get("itemName") or AmazonCatalogSyncService._first_attribute(attributes, "item_name") or AmazonCatalogSyncService._first_attribute(attributes, "title")
        asin = summary.get("asin") or payload.get("asin") or AmazonCatalogSyncService._first_attribute(attributes, "externally_assigned_product_identifier", "value")
        status = summary.get("status") or ",".join(summary.get("status") or []) if isinstance(summary.get("status"), list) else summary.get("status")
        return {
            "sku": sku,
            "asin": AmazonCatalogSyncService._clean(asin),
            "title": AmazonCatalogSyncService._clean(title),
            "status": status or "Mapped",
            "marketplace": marketplace,
            "marketplace_id": marketplace_id,
            "brand": summary.get("brand") or AmazonCatalogSyncService._first_attribute(attributes, "brand"),
            "product_type": summary.get("productType") or payload.get("productType"),
            "raw": payload,
        }

    @staticmethod
    def _first_attribute(attributes: dict[str, Any], key: str, nested_key: str | None = None) -> Any:
        values = attributes.get(key)
        if isinstance(values, list) and values:
            first = values[0]
            if isinstance(first, dict):
                if nested_key:
                    return first.get(nested_key)
                return first.get("value") or first.get("name") or first.get("text")
            return first
        return None

    @staticmethod
    def _resolve_or_build_product(db, listing: dict[str, Any], dry_run: bool) -> MasterProduct:
        sku = listing.get("sku")
        asin = listing.get("asin")
        title = listing.get("title")
        if sku:
            product = db.query(MasterProduct).filter(MasterProduct.primary_sku == sku).first()
            if product:
                return product
            channel = db.query(ProductChannel).filter(ProductChannel.sku == sku).first()
            if channel:
                product = db.query(MasterProduct).filter(MasterProduct.master_product_id == channel.master_product_id).first()
                if product:
                    return product
        if asin:
            channel = db.query(ProductChannel).filter(ProductChannel.asin == asin).first()
            if channel:
                product = db.query(MasterProduct).filter(MasterProduct.master_product_id == channel.master_product_id).first()
                if product:
                    return product
        product = MasterProduct(
            master_product_id=f"MP-AMZ-{uuid4().hex[:10].upper()}",
            brand=listing.get("brand"),
            product_family=listing.get("product_type") or "Amazon Catalog",
            primary_sku=sku,
            name=title or sku or asin or "Amazon Product",
            status="Active",
            lifecycle_stage="Discovered",
            source="amazon_catalog_sync",
            raw={"asin": asin, "sku": sku, "marketplace": listing.get("marketplace"), "marketplace_id": listing.get("marketplace_id")},
            active=True,
        )
        if not dry_run:
            db.add(product)
            db.flush()
        return product

    @staticmethod
    def _upsert_channel(db, product: MasterProduct, listing: dict[str, Any], dry_run: bool) -> str:
        sku = listing.get("sku")
        asin = listing.get("asin")
        marketplace = listing.get("marketplace")
        channel = None
        if asin:
            channel = db.query(ProductChannel).filter(ProductChannel.channel.ilike("%Amazon%"), ProductChannel.asin == asin).first()
        if not channel and sku:
            channel = db.query(ProductChannel).filter(ProductChannel.channel.ilike("%Amazon%"), ProductChannel.sku == sku).first()
        if not channel:
            channel = ProductChannel(
                master_product_id=product.master_product_id,
                brand=listing.get("brand") or product.brand,
                primary_sku=product.primary_sku,
                channel="Amazon",
                marketplace=marketplace,
                channel_product_id=asin,
                channel_listing_id=asin,
                asin=asin,
                sku=sku,
                status=listing.get("status") or "Mapped",
                raw=listing,
            )
            if not dry_run:
                db.add(channel)
            return "created"

        changed = False
        updates = {
            "master_product_id": product.master_product_id,
            "brand": listing.get("brand") or product.brand,
            "primary_sku": product.primary_sku,
            "marketplace": marketplace,
            "channel_product_id": asin,
            "channel_listing_id": asin,
            "asin": asin,
            "sku": sku,
            "status": listing.get("status") or "Mapped",
        }
        for attr, value in updates.items():
            if value and getattr(channel, attr, None) != value:
                if not dry_run:
                    setattr(channel, attr, value)
                changed = True
        if not dry_run:
            raw = channel.raw if isinstance(channel.raw, dict) else {}
            raw.update({"amazon_catalog_sync": listing, "last_catalog_sync_at": datetime.utcnow().isoformat()})
            channel.raw = raw
            channel.updated_at = datetime.utcnow()
        return "updated" if changed else "unchanged"

    @staticmethod
    def _clean(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
