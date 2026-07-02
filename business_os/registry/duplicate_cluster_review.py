"""Duplicate cluster review.

Read-only grouping for registry cleanup. This intentionally does not merge.
"""

from __future__ import annotations

import re
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any

from database import SessionLocal
from business_registry.models import MasterProduct, ProductChannel


_VARIANT_WORDS = {
    "small", "medium", "large", "xl", "good", "bad", "both", "black", "white", "gold", "silver", "blue", "pink", "green", "red",
    "mini", "set", "single", "pair", "bundle", "left", "right", "round", "square", "rectangle", "rectangular"
}
_STOP_WORDS = {"for", "and", "with", "the", "a", "an", "of", "to", "in", "on", "by", "new", "gift", "unique", "cute", "collectible"}


class DuplicateClusterReviewService:
    version = "business-os-1.0.0-duplicate-clusters"

    @classmethod
    def review(cls, limit: int = 500, min_cluster_size: int = 2) -> dict[str, Any]:
        db = SessionLocal()
        try:
            products = db.query(MasterProduct).order_by(MasterProduct.name.asc()).limit(limit).all()
            channels = db.query(ProductChannel).all()
            channel_map: dict[str, list[ProductChannel]] = defaultdict(list)
            for channel in channels:
                channel_map[channel.master_product_id].append(channel)

            buckets: dict[str, list[MasterProduct]] = defaultdict(list)
            for product in products:
                key = cls._family_key(product)
                if key:
                    buckets[key].append(product)

            clusters = []
            for key, rows in buckets.items():
                if len(rows) < min_cluster_size:
                    continue
                clusters.append(cls._cluster_payload(key, rows, channel_map))

            clusters.sort(key=lambda c: (c["risk_rank"], -c["count"], c["cluster_key"]))
            return {"status": "OK", "version": cls.version, "clusters": clusters, "cluster_count": len(clusters), "product_count_checked": len(products)}
        finally:
            db.close()

    @classmethod
    def _cluster_payload(cls, key: str, rows: list[MasterProduct], channel_map: dict[str, list[ProductChannel]]) -> dict[str, Any]:
        names = [p.name or "" for p in rows]
        exact_title_groups = defaultdict(list)
        for p in rows:
            exact_title_groups[cls._normalize_title(p.name or "")].append(p.master_product_id)
        exact_duplicate_count = sum(1 for ids in exact_title_groups.values() if len(ids) > 1)
        variants = [cls._variant_tokens(p.name or "") for p in rows]
        has_variant_signals = any(v for v in variants)
        classified = [cls._variant_classification(p) for p in rows]
        classified_count = sum(1 for item in classified if item)
        channels = [cls._channel_summary(channel_map.get(p.master_product_id, [])) for p in rows]
        suggestion = "REVIEW"
        risk_rank = 2
        if exact_duplicate_count and not has_variant_signals:
            suggestion = "LIKELY_DUPLICATE"
            risk_rank = 0
        elif has_variant_signals or classified_count:
            suggestion = "LIKELY_VARIANT_FAMILY"
            risk_rank = 1
        return {
            "cluster_key": key,
            "count": len(rows),
            "suggestion": suggestion,
            "risk_rank": risk_rank,
            "exact_duplicate_title_groups": exact_duplicate_count,
            "variant_signal_count": sum(1 for v in variants if v),
            "classified_variant_count": classified_count,
            "products": [
                {
                    "master_product_id": p.master_product_id,
                    "name": p.name,
                    "brand": p.brand,
                    "product_family": p.product_family,
                    "primary_sku": p.primary_sku,
                    "status": p.status,
                    "variant_tokens": cls._variant_tokens(p.name or ""),
                    "variant_classification": cls._variant_classification(p),
                    "channels": cls._channel_summary(channel_map.get(p.master_product_id, [])),
                }
                for p in rows
            ],
            "notes": cls._notes(names, suggestion),
        }

    @staticmethod
    def _variant_classification(product: MasterProduct) -> dict[str, Any] | None:
        raw = product.raw if isinstance(product.raw, dict) else {}
        value = raw.get("variant_classification")
        return value if isinstance(value, dict) else None

    @staticmethod
    def _channel_summary(channels: list[ProductChannel]) -> list[dict[str, Any]]:
        return [{"channel": c.channel, "marketplace": c.marketplace, "asin": c.asin, "sku": c.sku, "status": c.status} for c in channels]

    @classmethod
    def _family_key(cls, product: MasterProduct) -> str:
        raw = product.raw if isinstance(product.raw, dict) else {}
        classification = raw.get("variant_classification") if isinstance(raw.get("variant_classification"), dict) else {}
        if classification.get("product_family_group"):
            return cls._normalize_title(classification["product_family_group"])
        return cls._base_title(product.name or "")

    @classmethod
    def _base_title(cls, title: str) -> str:
        text = cls._normalize_title(title)
        tokens = [t for t in text.split() if t not in _VARIANT_WORDS and t not in _STOP_WORDS]
        return " ".join(tokens[:8])

    @staticmethod
    def _normalize_title(title: str) -> str:
        text = title.lower()
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _variant_tokens(title: str) -> list[str]:
        tokens = set(re.findall(r"[a-z0-9]+", title.lower()))
        return sorted(tokens.intersection(_VARIANT_WORDS))

    @staticmethod
    def _notes(names: list[str], suggestion: str) -> list[str]:
        if suggestion == "LIKELY_VARIANT_FAMILY":
            return ["Variant signals detected. Do not merge automatically."]
        if suggestion == "LIKELY_DUPLICATE":
            return ["Repeated titles without obvious variant signals. Review as possible duplicate."]
        return ["Similar title cluster. Human review required."]
