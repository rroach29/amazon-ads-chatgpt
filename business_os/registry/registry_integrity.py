"""Business OS Registry Integrity Audit.

Read-only diagnostics for MasterProduct and ProductChannel data quality.
No merges, deletes, archives, or repairs happen in this service.
"""

from __future__ import annotations

import re
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import func

from database import SessionLocal
from business_registry.models import MasterProduct, ProductChannel


class RegistryIntegrityService:
    version = "business-os-0.9.2-variation-family-safety"

    @classmethod
    def audit(cls, limit: int = 100) -> dict[str, Any]:
        db = SessionLocal()
        try:
            limit = max(1, min(limit, 500))
            master_count = db.query(MasterProduct).count()
            active_master_count = db.query(MasterProduct).filter(MasterProduct.active == True).count()  # noqa: E712
            channel_count = db.query(ProductChannel).count()
            by_channel = cls._counts_by(db, ProductChannel.channel)
            by_marketplace = cls._counts_by_marketplace(db)
            orphan_channels = cls._orphan_channels(db, limit)
            products_without_identities = cls._products_without_identities(db, limit)
            products_with_multiple_identities = cls._products_with_multiple_identities(db, limit)
            duplicate_asins = cls._duplicate_field(db, field="asin", same_marketplace=True, limit=limit)
            duplicate_skus = cls._duplicate_field(db, field="sku", same_marketplace=True, limit=limit)
            duplicate_titles = cls._duplicate_titles(db, limit)
            duplicate_base_titles = cls._duplicate_base_titles(db, limit)
            duplicate_primary_skus = cls._duplicate_master_field(db, "primary_sku", limit)
            missing_data = cls._missing_data(db, limit)
            early_sync_products = cls._early_sync_products(db, limit)
            merge_candidates = cls._merge_candidates(db, limit)
            issue_counts = {
                "orphan_channels": len(orphan_channels),
                "products_without_identities": len(products_without_identities),
                "duplicate_asin_groups": len(duplicate_asins),
                "duplicate_sku_groups": len(duplicate_skus),
                "duplicate_title_groups": len(duplicate_titles),
                "duplicate_base_title_groups": len(duplicate_base_titles),
                "duplicate_primary_sku_groups": len(duplicate_primary_skus),
                "missing_primary_sku": missing_data["missing_primary_sku_count"],
                "missing_brand": missing_data["missing_brand_count"],
                "missing_name": missing_data["missing_name_count"],
                "early_listings_sync_products": early_sync_products["count"],
                "merge_candidates": len(merge_candidates),
            }
            score = cls._health_score(master_count=master_count, channel_count=channel_count, issue_counts=issue_counts)
            return {
                "status": "OK",
                "version": cls.version,
                "read_only": True,
                "health_score": score,
                "summary": {"master_products": master_count, "active_master_products": active_master_count, "marketplace_identities": channel_count, "by_channel": by_channel, "by_channel_marketplace": by_marketplace, "issue_counts": issue_counts},
                "orphans": {"product_channels": orphan_channels},
                "products_without_identities": products_without_identities,
                "products_with_multiple_identities": products_with_multiple_identities,
                "duplicates": {"asin_by_channel_marketplace": duplicate_asins, "sku_by_channel_marketplace": duplicate_skus, "master_title": duplicate_titles, "master_base_title": duplicate_base_titles, "master_primary_sku": duplicate_primary_skus},
                "missing_data": missing_data,
                "early_listings_sync_products": early_sync_products,
                "merge_candidates": merge_candidates,
                "next_step": "Review merge_candidates first. Variation-family matches are not safe merges; they need parent/family modeling or manual approval.",
            }
        finally:
            db.close()

    @staticmethod
    def _counts_by(db, column) -> dict[str, int]:
        rows = db.query(column, func.count(ProductChannel.id)).group_by(column).all()
        return {str(key or "unknown"): count for key, count in rows}

    @staticmethod
    def _counts_by_marketplace(db) -> list[dict[str, Any]]:
        rows = db.query(ProductChannel.channel, ProductChannel.marketplace, func.count(ProductChannel.id)).group_by(ProductChannel.channel, ProductChannel.marketplace).all()
        return [{"channel": channel or "unknown", "marketplace": marketplace or "unknown", "count": count} for channel, marketplace, count in rows]

    @staticmethod
    def _orphan_channels(db, limit: int) -> list[dict[str, Any]]:
        product_ids = {row[0] for row in db.query(MasterProduct.master_product_id).all()}
        output = []
        for row in db.query(ProductChannel).limit(10000).all():
            if row.master_product_id not in product_ids:
                output.append(RegistryIntegrityService._channel_payload(row))
            if len(output) >= limit:
                break
        return output

    @staticmethod
    def _products_without_identities(db, limit: int) -> list[dict[str, Any]]:
        rows = db.query(MasterProduct).outerjoin(ProductChannel, MasterProduct.master_product_id == ProductChannel.master_product_id).group_by(MasterProduct.id).having(func.count(ProductChannel.id) == 0).limit(limit).all()
        return [RegistryIntegrityService._product_payload(row) for row in rows]

    @staticmethod
    def _products_with_multiple_identities(db, limit: int) -> list[dict[str, Any]]:
        rows = db.query(ProductChannel.master_product_id, func.count(ProductChannel.id)).group_by(ProductChannel.master_product_id).having(func.count(ProductChannel.id) > 1).order_by(func.count(ProductChannel.id).desc()).limit(limit).all()
        output = []
        for master_product_id, count in rows:
            product = db.query(MasterProduct).filter(MasterProduct.master_product_id == master_product_id).first()
            channels = db.query(ProductChannel).filter(ProductChannel.master_product_id == master_product_id).limit(20).all()
            output.append({"master_product_id": master_product_id, "product_name": product.name if product else None, "identity_count": count, "identities": [RegistryIntegrityService._channel_payload(c) for c in channels]})
        return output

    @staticmethod
    def _duplicate_field(db, field: str, same_marketplace: bool, limit: int) -> list[dict[str, Any]]:
        column = getattr(ProductChannel, field)
        group_cols = [ProductChannel.channel, ProductChannel.marketplace, column] if same_marketplace else [column]
        rows = db.query(*group_cols, func.count(ProductChannel.id)).filter(column.isnot(None), column != "").group_by(*group_cols).having(func.count(ProductChannel.id) > 1).limit(limit).all()
        output = []
        for row in rows:
            if same_marketplace:
                channel, marketplace, value, count = row
                matches = db.query(ProductChannel).filter(ProductChannel.channel == channel, ProductChannel.marketplace == marketplace, column == value).limit(20).all()
                output.append({"channel": channel, "marketplace": marketplace, field: value, "count": count, "rows": [RegistryIntegrityService._channel_payload(m) for m in matches]})
            else:
                value, count = row
                matches = db.query(ProductChannel).filter(column == value).limit(20).all()
                output.append({field: value, "count": count, "rows": [RegistryIntegrityService._channel_payload(m) for m in matches]})
        return output

    @staticmethod
    def _duplicate_titles(db, limit: int) -> list[dict[str, Any]]:
        rows = db.query(MasterProduct.name, func.count(MasterProduct.id)).filter(MasterProduct.name.isnot(None), MasterProduct.name != "").group_by(MasterProduct.name).having(func.count(MasterProduct.id) > 1).limit(limit).all()
        output = []
        for title, count in rows:
            products = db.query(MasterProduct).filter(MasterProduct.name == title).limit(20).all()
            output.append({"title": title, "count": count, "products": [RegistryIntegrityService._product_payload(p) for p in products]})
        return output

    @staticmethod
    def _duplicate_base_titles(db, limit: int) -> list[dict[str, Any]]:
        buckets: dict[str, list[MasterProduct]] = defaultdict(list)
        for product in db.query(MasterProduct).limit(5000).all():
            key = RegistryIntegrityService._base_title(product.name or "")
            if key:
                buckets[key].append(product)
        output = []
        for key, products in buckets.items():
            if len(products) > 1:
                output.append({"base_title": key, "count": len(products), "products": [RegistryIntegrityService._product_payload(p) for p in products[:20]], "note": "Base-title duplicates may be legitimate variations, not duplicate products."})
        output.sort(key=lambda row: row["count"], reverse=True)
        return output[:limit]

    @staticmethod
    def _duplicate_master_field(db, field: str, limit: int) -> list[dict[str, Any]]:
        column = getattr(MasterProduct, field)
        rows = db.query(column, func.count(MasterProduct.id)).filter(column.isnot(None), column != "").group_by(column).having(func.count(MasterProduct.id) > 1).limit(limit).all()
        output = []
        for value, count in rows:
            products = db.query(MasterProduct).filter(column == value).limit(20).all()
            output.append({field: value, "count": count, "products": [RegistryIntegrityService._product_payload(p) for p in products]})
        return output

    @staticmethod
    def _missing_data(db, limit: int) -> dict[str, Any]:
        missing_primary = db.query(MasterProduct).filter((MasterProduct.primary_sku.is_(None)) | (MasterProduct.primary_sku == "")).limit(limit).all()
        missing_brand = db.query(MasterProduct).filter((MasterProduct.brand.is_(None)) | (MasterProduct.brand == "")).limit(limit).all()
        missing_name = db.query(MasterProduct).filter((MasterProduct.name.is_(None)) | (MasterProduct.name == "")).limit(limit).all()
        return {"missing_primary_sku_count": db.query(MasterProduct).filter((MasterProduct.primary_sku.is_(None)) | (MasterProduct.primary_sku == "")).count(), "missing_brand_count": db.query(MasterProduct).filter((MasterProduct.brand.is_(None)) | (MasterProduct.brand == "")).count(), "missing_name_count": db.query(MasterProduct).filter((MasterProduct.name.is_(None)) | (MasterProduct.name == "")).count(), "samples_missing_primary_sku": [RegistryIntegrityService._product_payload(p) for p in missing_primary], "samples_missing_brand": [RegistryIntegrityService._product_payload(p) for p in missing_brand], "samples_missing_name": [RegistryIntegrityService._product_payload(p) for p in missing_name]}

    @staticmethod
    def _early_sync_products(db, limit: int) -> dict[str, Any]:
        rows = db.query(MasterProduct).filter(MasterProduct.source.in_(["amazon_listings_discovery", "amazon_identity_sync"])).limit(limit).all()
        count = db.query(MasterProduct).filter(MasterProduct.source.in_(["amazon_listings_discovery", "amazon_identity_sync"])).count()
        return {"count": count, "samples": [RegistryIntegrityService._product_payload(p) for p in rows]}

    @staticmethod
    def _merge_candidates(db, limit: int) -> list[dict[str, Any]]:
        products = db.query(MasterProduct).limit(5000).all()
        channels_by_product: dict[str, list[ProductChannel]] = defaultdict(list)
        for channel in db.query(ProductChannel).limit(20000).all():
            channels_by_product[channel.master_product_id].append(channel)
        candidates = []
        seen = set()
        for i, left in enumerate(products):
            for right in products[i + 1:]:
                key = tuple(sorted([left.master_product_id, right.master_product_id]))
                if key in seen:
                    continue
                seen.add(key)
                score, reasons, candidate_type = RegistryIntegrityService._candidate_score(left, right, channels_by_product)
                if score >= 65:
                    candidates.append({"confidence": score, "candidate_type": candidate_type, "reasons": reasons, "recommended_action": RegistryIntegrityService._recommended_action(score, candidate_type), "keep_candidate": RegistryIntegrityService._product_payload(RegistryIntegrityService._choose_keeper(left, right, channels_by_product)), "left": RegistryIntegrityService._product_payload(left), "right": RegistryIntegrityService._product_payload(right)})
        candidates.sort(key=lambda row: (row["candidate_type"] == "exact_duplicate", row["confidence"]), reverse=True)
        return candidates[:limit]

    @staticmethod
    def _recommended_action(score: int, candidate_type: str) -> str:
        if candidate_type == "variation_family":
            return "variation_family_review_not_safe_merge"
        if score >= 98 and candidate_type == "exact_duplicate":
            return "safe_merge_candidate"
        return "review_merge"

    @staticmethod
    def _candidate_score(left: MasterProduct, right: MasterProduct, channels_by_product: dict[str, list[ProductChannel]]) -> tuple[int, list[str], str]:
        score = 0
        reasons = []
        variation_signals = 0
        exact_signals = 0
        left_channels = channels_by_product.get(left.master_product_id, [])
        right_channels = channels_by_product.get(right.master_product_id, [])
        left_skus = {c.sku for c in left_channels if c.sku}
        right_skus = {c.sku for c in right_channels if c.sku}
        left_parent_skus = RegistryIntegrityService._parent_skus(left, left_channels)
        right_parent_skus = RegistryIntegrityService._parent_skus(right, right_channels)
        left_asins = {(c.channel, c.marketplace, c.asin) for c in left_channels if c.asin}
        right_asins = {(c.channel, c.marketplace, c.asin) for c in right_channels if c.asin}
        left_source = left.source or ""
        right_source = right.source or ""
        left_base = RegistryIntegrityService._base_title(left.name or "")
        right_base = RegistryIntegrityService._base_title(right.name or "")
        different_titles = bool(left.name and right.name and left.name.strip() != right.name.strip())
        variation_values_differ = RegistryIntegrityService._variation_values(left.name) != RegistryIntegrityService._variation_values(right.name)

        if left.primary_sku and right.primary_sku and left.primary_sku == right.primary_sku:
            score += 45; exact_signals += 1; reasons.append("same primary SKU")
        if left_skus & right_skus:
            score += 45; exact_signals += 1; reasons.append("same marketplace SKU")
        if left_asins & right_asins:
            score += 55; exact_signals += 1; reasons.append("same marketplace ASIN")
        if left_parent_skus & right_parent_skus:
            score += 35; variation_signals += 1; reasons.append("same variation parent SKU")
        if left.primary_sku and left.primary_sku in right_parent_skus:
            score += 30; variation_signals += 1; reasons.append("left primary SKU is right parent SKU")
        if right.primary_sku and right.primary_sku in left_parent_skus:
            score += 30; variation_signals += 1; reasons.append("right primary SKU is left parent SKU")
        if left.name and right.name:
            title_score = SequenceMatcher(None, RegistryIntegrityService._normalize(left.name), RegistryIntegrityService._normalize(right.name)).ratio()
            if title_score >= 0.98 and not different_titles:
                score += 35; exact_signals += 1; reasons.append("identical normalized title")
            elif title_score >= 0.84:
                score += 20; variation_signals += 1; reasons.append("similar title")
            elif title_score >= 0.74:
                score += 12; variation_signals += 1; reasons.append("loose title similarity")
        if left_base and right_base and left_base == right_base:
            score += 30; variation_signals += 1; reasons.append("same normalized base title")
        if variation_values_differ:
            variation_signals += 1; reasons.append("different size/color variation value")
        if left.brand and right.brand and left.brand.lower() == right.brand.lower():
            score += 10; reasons.append("same brand")
        if left.product_family and right.product_family and left.product_family.lower() == right.product_family.lower():
            score += 10; reasons.append("same product family")
        if left_source in {"amazon_listings_discovery", "amazon_identity_sync"} and right_source in {"amazon_listings_discovery", "amazon_identity_sync"}:
            if left_base and right_base and SequenceMatcher(None, left_base, right_base).ratio() >= 0.82:
                score += 18; variation_signals += 1; reasons.append("both early Amazon sync products with similar base title")

        candidate_type = "exact_duplicate" if exact_signals and not variation_values_differ and not (variation_signals and different_titles) else "variation_family"
        if candidate_type == "variation_family":
            score = min(score, 94)
        return min(score, 100), reasons, candidate_type

    @staticmethod
    def _parent_skus(product: MasterProduct, channels: list[ProductChannel]) -> set[str]:
        output = set()
        if product.primary_sku:
            output.add(product.primary_sku)
        for channel in channels:
            raw = channel.raw if isinstance(channel.raw, dict) else {}
            listing = raw.get("listing") or raw.get("listings_items_api") or {}
            if isinstance(listing, dict):
                parent = listing.get("parent_sku") or RegistryIntegrityService._raw_parent_sku(listing.get("raw") or listing)
                if parent:
                    output.add(parent)
        return output

    @staticmethod
    def _raw_parent_sku(raw: dict[str, Any]) -> str | None:
        attrs = raw.get("attributes") if isinstance(raw, dict) else None
        if not isinstance(attrs, dict):
            return None
        relationships = attrs.get("child_parent_sku_relationship") or []
        for row in relationships:
            if isinstance(row, dict) and row.get("parent_sku"):
                return row.get("parent_sku")
        return None

    @staticmethod
    def _choose_keeper(left: MasterProduct, right: MasterProduct, channels_by_product: dict[str, list[ProductChannel]]) -> MasterProduct:
        left_channels = len(channels_by_product.get(left.master_product_id, []))
        right_channels = len(channels_by_product.get(right.master_product_id, []))
        if left_channels != right_channels:
            return left if left_channels > right_channels else right
        if left.source != "amazon_listings_discovery" and right.source == "amazon_listings_discovery":
            return left
        if right.source != "amazon_listings_discovery" and left.source == "amazon_listings_discovery":
            return right
        if left.created_at and right.created_at:
            return left if left.created_at <= right.created_at else right
        return left

    @staticmethod
    def _variation_values(text: str | None) -> set[str]:
        text = str(text or "").lower()
        values = set(re.findall(r"\(([^)]*)\)", text))
        colors_sizes = {"medium", "large", "small", "brown", "black", "white", "blue", "red", "green", "pink", "purple", "yellow", "orange", "grey", "gray", "gold", "silver"}
        for word in re.sub(r"[^a-z0-9]+", " ", text).split():
            if word in colors_sizes:
                values.add(word)
        return values

    @staticmethod
    def _base_title(text: str) -> str:
        text = RegistryIntegrityService._normalize(text)
        stop = {"medium", "large", "small", "brown", "black", "white", "blue", "red", "green", "pink", "purple", "yellow", "orange", "grey", "gray", "gold", "silver", "size", "color", "colour"}
        return " ".join([word for word in text.split() if word not in stop])[:140]

    @staticmethod
    def _normalize(text: str) -> str:
        text = str(text or "").lower()
        text = re.sub(r"\([^)]*\)", " ", text)
        text = re.sub(r"[^a-z0-9]+", " ", text)
        stop = {"the", "and", "with", "for", "gift", "gifts", "unique", "style", "included", "a", "an", "of", "to", "in", "on"}
        return " ".join([word for word in text.split() if word not in stop])

    @staticmethod
    def _health_score(master_count: int, channel_count: int, issue_counts: dict[str, int]) -> int:
        if master_count == 0:
            return 0
        penalty = 0
        penalty += min(25, issue_counts["orphan_channels"] * 3)
        penalty += min(25, issue_counts["products_without_identities"] * 2)
        penalty += min(20, issue_counts["duplicate_asin_groups"] * 5)
        penalty += min(20, issue_counts["duplicate_sku_groups"] * 4)
        penalty += min(15, issue_counts["duplicate_title_groups"] * 3)
        penalty += min(15, issue_counts.get("duplicate_base_title_groups", 0) * 2)
        penalty += min(15, issue_counts["merge_candidates"] * 2)
        penalty += min(10, issue_counts["missing_primary_sku"])
        return max(0, min(100, 100 - penalty))

    @staticmethod
    def _product_payload(product: MasterProduct) -> dict[str, Any]:
        return {"master_product_id": product.master_product_id, "name": product.name, "brand": product.brand, "product_family": product.product_family, "primary_sku": product.primary_sku, "status": product.status, "lifecycle_stage": product.lifecycle_stage, "source": product.source, "active": product.active, "created_at": product.created_at.isoformat() if product.created_at else None}

    @staticmethod
    def _channel_payload(channel: ProductChannel) -> dict[str, Any]:
        return {"id": channel.id, "master_product_id": channel.master_product_id, "channel": channel.channel, "marketplace": channel.marketplace, "asin": channel.asin, "sku": channel.sku, "channel_product_id": channel.channel_product_id, "channel_listing_id": channel.channel_listing_id, "status": channel.status, "created_at": channel.created_at.isoformat() if channel.created_at else None}
