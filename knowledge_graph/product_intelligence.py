"""
Business OS v7.0 — Product Intelligence

First pass product intelligence. Today, product identity is inferred from campaign
and search-term language because the project does not yet ingest Seller Central
SKU/ASIN/product catalog data. The service is intentionally designed so future
catalog integrations can replace inference with real product IDs without changing
Mission Control or optimizer contracts.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .relationship_service import RelationshipService


class ProductIntelligenceService:
    PRODUCT_RULES = {
        "photo_crystal": ["photo", "crystal", "pet photo", "memorial crystal"],
        "pet_memorial": ["pet", "memorial", "dog memorial", "cat memorial", "loss of"],
        "slate_memorial": ["slate"],
        "ornament": ["ornament"],
        "keychain": ["keychain"],
    }

    @staticmethod
    def infer_product_family(text: str | None) -> str:
        value = (text or "").lower()
        for family, tokens in ProductIntelligenceService.PRODUCT_RULES.items():
            if any(token in value for token in tokens):
                return family
        return "unknown"

    @staticmethod
    def product_summary(country_code: str | None = None, profile_id: str | None = None) -> dict[str, Any]:
        graph = RelationshipService.build_graph(country_code=country_code, profile_id=profile_id, limit=500)
        product_stats = defaultdict(lambda: {
            "campaigns": set(),
            "search_terms": set(),
            "spend": 0.0,
            "sales": 0.0,
            "orders": 0,
            "clicks": 0,
            "impressions": 0,
        })

        for node in graph.get("nodes", []):
            node_type = node.get("type")
            attrs = node.get("attributes") or {}
            label = node.get("label") or ""
            family = ProductIntelligenceService.infer_product_family(label)
            if node_type == "campaign":
                product_stats[family]["campaigns"].add(attrs.get("campaign_id") or node.get("id"))
                product_stats[family]["spend"] += float(attrs.get("spend") or 0)
                product_stats[family]["sales"] += float(attrs.get("sales") or 0)
                product_stats[family]["orders"] += int(attrs.get("orders") or 0)
                product_stats[family]["clicks"] += int(attrs.get("clicks") or 0)
                product_stats[family]["impressions"] += int(attrs.get("impressions") or 0)
            elif node_type == "search_term":
                family = ProductIntelligenceService.infer_product_family(label)
                product_stats[family]["search_terms"].add(label)

        products = []
        for family, stats in product_stats.items():
            spend = round(stats["spend"], 2)
            sales = round(stats["sales"], 2)
            acos = round((spend / sales) * 100, 2) if sales else None
            roas = round(sales / spend, 2) if spend else None
            products.append({
                "product_family": family,
                "campaign_count": len(stats["campaigns"]),
                "search_term_count": len(stats["search_terms"]),
                "spend": spend,
                "sales": sales,
                "acos": acos,
                "roas": roas,
                "orders": stats["orders"],
                "clicks": stats["clicks"],
                "impressions": stats["impressions"],
                "inference_method": "campaign_and_search_term_language",
            })

        products.sort(key=lambda item: item.get("spend") or 0, reverse=True)
        return {
            "status": graph.get("status", "OK"),
            "scope": graph.get("scope"),
            "product_count": len(products),
            "products": products,
            "note": "Product families are inferred until Seller Central catalog/SKU data is integrated.",
        }
