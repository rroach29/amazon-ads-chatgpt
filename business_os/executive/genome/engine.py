"""Executive Brain v2.0 — Product Genome Engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from business_os.platform.evidence.models import EvidenceSet
from business_os.platform.scoring.base import BaseScoringEngine
from business_os.platform.scoring.models import ScoreComponent
from business_os.executive.genome.repository import ProductGenomeRepository


class ProductGenomeEngine:
    version = "executive-brain-2.0"

    @classmethod
    def calculate_for_master_product(cls, repo: ProductGenomeRepository, master_product) -> dict[str, Any]:
        channels = repo.channels_for(master_product.master_product_id)
        seller = repo.seller_central_metrics(master_product.master_product_id)
        ads = repo.campaign_metrics(master_product.master_product_id)

        metrics = cls._metrics(seller, ads, channels)
        evidence = cls._evidence(master_product, seller, ads, channels)

        profitability = cls._profitability(metrics)
        organic_strength = cls._organic_strength(metrics)
        advertising_dependency = cls._advertising_dependency(metrics)
        growth_momentum = cls._growth_momentum(metrics)
        confidence = cls._confidence(master_product, seller, ads, channels)

        health_result = BaseScoringEngine.combine(
            "Product Health",
            components=[
                ScoreComponent(name="Profitability", score=profitability, weight=0.25, confidence=confidence / 100),
                ScoreComponent(name="Organic Strength", score=organic_strength, weight=0.25, confidence=confidence / 100),
                ScoreComponent(name="Advertising Independence", score=100 - advertising_dependency, weight=0.20, confidence=confidence / 100),
                ScoreComponent(name="Growth Momentum", score=growth_momentum, weight=0.15, confidence=confidence / 100),
                ScoreComponent(name="Data Confidence", score=confidence, weight=0.15, confidence=confidence / 100),
            ],
            explanation="Product Health v1 combines profitability, organic strength, advertising independence, momentum, and confidence.",
        )

        lifecycle = cls._lifecycle(metrics, health_result.score, organic_strength, advertising_dependency)
        archetype = cls._archetype(metrics, health_result.score, organic_strength, advertising_dependency)
        objective = cls._objective(lifecycle, archetype, advertising_dependency, organic_strength)
        opportunity = cls._top_opportunity(metrics, lifecycle, archetype, advertising_dependency, organic_strength)
        risk = cls._top_risk(metrics, advertising_dependency, confidence)
        recommendation = cls._recommendation(opportunity, risk, objective)
        summary = cls._summary(master_product, health_result.score, lifecycle, archetype, objective)

        return {
            "master_product_id": master_product.master_product_id,
            "brand": master_product.brand,
            "product_family": master_product.product_family,
            "primary_sku": master_product.primary_sku,
            "name": master_product.name,
            "product_health": health_result.score,
            "organic_strength": organic_strength,
            "advertising_dependency_index": advertising_dependency,
            "profitability": profitability,
            "growth_momentum": growth_momentum,
            "confidence": confidence,
            "lifecycle_stage": lifecycle,
            "archetype": archetype,
            "objective": objective,
            "top_opportunity": opportunity,
            "top_risk": risk,
            "executive_recommendation": recommendation,
            "evidence": evidence.to_list(),
            "metrics": metrics,
            "summary": summary,
            "score_version": cls.version,
            "calculated_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

    @staticmethod
    def _metrics(seller: dict, ads: dict, channels: list) -> dict[str, Any]:
        revenue = float(seller.get("revenue") or 0)
        orders = int(seller.get("orders") or 0)
        units = int(seller.get("units") or 0)
        sessions = int(seller.get("sessions") or 0)
        ad_spend = float(ads.get("ad_spend") or 0)
        attributed_sales = float(ads.get("attributed_sales_7d") or 0)
        clicks = int(ads.get("clicks") or 0)
        impressions = int(ads.get("impressions") or 0)

        return {
            "revenue": round(revenue, 2),
            "orders": orders,
            "units": units,
            "sessions": sessions,
            "page_views": int(seller.get("page_views") or 0),
            "ad_spend": round(ad_spend, 2),
            "ad_attributed_sales_7d": round(attributed_sales, 2),
            "ad_attributed_orders_7d": int(ads.get("attributed_orders_7d") or 0),
            "clicks": clicks,
            "impressions": impressions,
            "conversion_rate": round(units / sessions, 4) if sessions else None,
            "tacos": round(ad_spend / revenue, 4) if revenue else None,
            "acos_7d": round(ad_spend / attributed_sales, 4) if attributed_sales else None,
            "ctr": round(clicks / impressions, 4) if impressions else None,
            "channel_count": len(channels),
            "mapped_channel_count": len([c for c in channels if c.status == "Mapped"]),
            "seller_rows": int(seller.get("rows") or 0),
            "campaign_rows": int(ads.get("rows") or 0),
            "seller_latest_date": str(seller.get("latest_date")) if seller.get("latest_date") else None,
            "ads_latest_date": str(ads.get("latest_date")) if ads.get("latest_date") else None,
        }

    @staticmethod
    def _evidence(master_product, seller: dict, ads: dict, channels: list) -> EvidenceSet:
        evidence = EvidenceSet()
        evidence.add("business_registry", "master_product_exists", master_product.master_product_id, 1.0, 1.0, "Product exists in the canonical Business Registry.")
        evidence.add("business_registry", "channel_count", len(channels), 0.5, 0.8, "Channel mappings indicate where this product can be sold.")
        evidence.add("seller_central", "seller_rows", seller.get("rows", 0), 1.0, 0.9 if seller.get("rows") else 0.3, "Seller Central rows linked through master_product_id.")
        evidence.add("amazon_ads", "campaign_rows", ads.get("rows", 0), 0.8, 0.8 if ads.get("rows") else 0.3, "Campaign rows linked through master_product_id.")
        return evidence

    @staticmethod
    def _profitability(metrics: dict) -> int:
        revenue = metrics["revenue"]
        ad_spend = metrics["ad_spend"]
        if revenue <= 0:
            return 25
        tacos = ad_spend / revenue
        return BaseScoringEngine.clamp(92 - (tacos * 180))

    @staticmethod
    def _organic_strength(metrics: dict) -> int:
        revenue = metrics["revenue"]
        sessions = metrics["sessions"]
        cvr = metrics["conversion_rate"]
        tacos = metrics["tacos"]

        if revenue <= 0:
            return 15

        score = 65
        if tacos is None or tacos <= 0.05:
            score += 20
        elif tacos <= 0.10:
            score += 12
        elif tacos <= 0.20:
            score += 3
        elif tacos <= 0.35:
            score -= 12
        else:
            score -= 25

        if cvr is not None:
            if cvr >= 0.08:
                score += 12
            elif cvr >= 0.03:
                score += 5
            elif cvr < 0.01:
                score -= 10

        if sessions < 25:
            score -= 8

        return BaseScoringEngine.clamp(score)

    @staticmethod
    def _advertising_dependency(metrics: dict) -> int:
        revenue = metrics["revenue"]
        ad_spend = metrics["ad_spend"]
        attributed_sales = metrics["ad_attributed_sales_7d"]

        if revenue <= 0:
            return 80 if ad_spend > 0 else 50

        tacos = ad_spend / revenue
        attributed_ratio = min((attributed_sales / revenue) if revenue else 0, 2.0)
        score = tacos * 180 + attributed_ratio * 18
        return BaseScoringEngine.clamp(score)

    @staticmethod
    def _growth_momentum(metrics: dict) -> int:
        # v2.0 placeholder until multi-period trend tables are connected.
        if metrics["revenue"] > 0 and metrics["orders"] > 0:
            return 60
        return 40

    @staticmethod
    def _confidence(master_product, seller: dict, ads: dict, channels: list) -> int:
        score = 45
        if master_product.primary_sku:
            score += 15
        if seller.get("rows"):
            score += 20
        if ads.get("rows"):
            score += 10
        if channels:
            score += 5
        return BaseScoringEngine.clamp(score, 10, 95)

    @staticmethod
    def _lifecycle(metrics: dict, health: int, organic: int, adi: int) -> str:
        if metrics["orders"] <= 2 and metrics["revenue"] < 150:
            return "Launch"
        if organic >= 82 and adi <= 35:
            return "Organic Leader"
        if health >= 80:
            return "Scaling"
        if metrics["revenue"] > 0 and health >= 55:
            return "Growth"
        if metrics["revenue"] > 0:
            return "Needs Attention"
        return "Unproven"

    @staticmethod
    def _archetype(metrics: dict, health: int, organic: int, adi: int) -> str:
        if organic >= 85 and adi <= 25:
            return "Organic Leader"
        if health >= 80 and metrics["revenue"] > 0:
            return "Emerging Winner"
        if metrics["revenue"] > 0 and adi >= 75:
            return "Advertising Dependent"
        if metrics["revenue"] > 0 and adi <= 45:
            return "Advertising Assisted"
        if metrics["revenue"] <= 0:
            return "Unproven"
        return "Growth Candidate"

    @staticmethod
    def _objective(lifecycle: str, archetype: str, adi: int, organic: int) -> str:
        if archetype == "Organic Leader":
            return "Protect organic strength while reducing unnecessary advertising"
        if adi >= 70:
            return "Reduce advertising dependency"
        if organic < 55:
            return "Improve organic strength"
        if lifecycle == "Launch":
            return "Validate demand and collect product signal"
        return "Grow profitably"

    @staticmethod
    def _top_opportunity(metrics: dict, lifecycle: str, archetype: str, adi: int, organic: int) -> dict[str, Any]:
        if archetype == "Organic Leader":
            return {
                "type": "ad_reduction_test",
                "title": "Test a small advertising reduction",
                "expected_impact": "Lower ad spend with low revenue risk",
                "confidence": 85,
                "reason": "Organic strength is high and advertising dependency is low.",
            }
        if adi >= 70:
            return {
                "type": "listing_conversion_work",
                "title": "Improve conversion before increasing advertising",
                "expected_impact": "Lower advertising dependency",
                "confidence": 78,
                "reason": "Advertising dependency is high relative to product revenue.",
            }
        if metrics["revenue"] > 0 and metrics["channel_count"] >= 4 and metrics["mapped_channel_count"] < 2:
            return {
                "type": "channel_mapping",
                "title": "Complete channel mappings",
                "expected_impact": "Unlock cross-channel intelligence",
                "confidence": 90,
                "reason": "The product exists in the Registry but has incomplete channel IDs.",
            }
        return {
            "type": "collect_more_signal",
            "title": "Collect more product-level signal",
            "expected_impact": "Improve Executive Brain confidence",
            "confidence": 60,
            "reason": "More linked product-level data is needed before recommending aggressive action.",
        }

    @staticmethod
    def _top_risk(metrics: dict, adi: int, confidence: int) -> dict[str, Any]:
        if adi >= 80:
            return {
                "type": "advertising_dependency",
                "title": "High advertising dependency",
                "severity": 90,
                "reason": "Sales may depend heavily on paid traffic.",
            }
        if confidence < 60:
            return {
                "type": "low_confidence",
                "title": "Limited linked product data",
                "severity": 65,
                "reason": "The Executive Brain needs more registry-linked data.",
            }
        if metrics["revenue"] > 0 and metrics["sessions"] > 50 and (metrics["conversion_rate"] or 0) < 0.01:
            return {
                "type": "conversion_risk",
                "title": "Low conversion risk",
                "severity": 75,
                "reason": "Traffic exists but conversion is weak.",
            }
        return {
            "type": "monitor",
            "title": "No major product risk detected",
            "severity": 30,
            "reason": "No high-severity risk was detected in v2.0.",
        }

    @staticmethod
    def _recommendation(opportunity: dict, risk: dict, objective: str) -> dict[str, Any]:
        return {
            "title": opportunity.get("title"),
            "objective": objective,
            "priority": "HIGH" if opportunity.get("confidence", 0) >= 80 else "MEDIUM",
            "reason": opportunity.get("reason"),
            "risk_to_watch": risk.get("title"),
            "approval_required": True,
        }

    @staticmethod
    def _summary(master_product, health: int, lifecycle: str, archetype: str, objective: str) -> str:
        return (
            f"{master_product.name} is classified as {archetype} in the {lifecycle} stage. "
            f"Product Health is {health}/100. Current objective: {objective}."
        )
