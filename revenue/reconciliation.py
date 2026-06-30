"""Business OS v9.0 — Organic vs Paid reconciliation service."""

from __future__ import annotations

from typing import Any

from revenue.engine import RevenueIntelligenceEngine


class RevenueReconciliationService:
    version = "9.0"

    @staticmethod
    def organic_vs_paid(window: str = "latest", country_code: str | None = None, profile_id: str | None = None) -> dict[str, Any]:
        marketplaces = RevenueIntelligenceEngine.marketplaces(window=window, country_code=country_code, profile_id=profile_id)
        products = RevenueIntelligenceEngine.products(window=window, country_code=country_code, profile_id=profile_id, limit=100)
        combined = marketplaces.get("combined", {}) if isinstance(marketplaces, dict) else {}
        seller_status = marketplaces.get("seller_central_data_status") if isinstance(marketplaces, dict) else "UNKNOWN"
        total = RevenueReconciliationService._safe_float(combined.get("total_revenue"))
        paid = RevenueReconciliationService._safe_float(combined.get("paid_revenue"))
        organic = RevenueReconciliationService._safe_float(combined.get("organic_revenue"))
        ad_spend = RevenueReconciliationService._safe_float(combined.get("ad_spend"))
        return {
            "status": "OK" if seller_status != "AWAITING_SELLER_CENTRAL_DATA" else "AWAITING_SELLER_CENTRAL_DATA",
            "version": RevenueReconciliationService.version,
            "data_context": marketplaces.get("data_context") if isinstance(marketplaces, dict) else None,
            "seller_central_data_status": seller_status,
            "summary": {
                "total_revenue": round(total, 2),
                "paid_revenue": round(paid, 2),
                "organic_revenue": round(organic, 2),
                "ad_spend": round(ad_spend, 2),
                "organic_ratio": RevenueReconciliationService._ratio(organic, total),
                "paid_ratio": RevenueReconciliationService._ratio(paid, total),
                "tacos": RevenueReconciliationService._ratio(ad_spend, total),
                "advertising_dependency": RevenueReconciliationService._dependency_label(paid, total),
                "confidence": combined.get("confidence"),
            },
            "marketplaces": marketplaces.get("marketplaces", []) if isinstance(marketplaces, dict) else [],
            "products": products.get("products", []) if isinstance(products, dict) else [],
            "top_organic_strength": products.get("top_organic_strength", []) if isinstance(products, dict) else [],
            "most_ad_dependent": products.get("most_ad_dependent", []) if isinstance(products, dict) else [],
            "executive_narrative": RevenueReconciliationService._narrative(total, paid, organic, ad_spend, seller_status),
        }

    @staticmethod
    def executive_snapshot(window: str = "latest", country_code: str | None = None, profile_id: str | None = None) -> dict[str, Any]:
        data = RevenueReconciliationService.organic_vs_paid(window=window, country_code=country_code, profile_id=profile_id)
        summary = data.get("summary", {})
        return {
            "status": data.get("status"),
            "version": RevenueReconciliationService.version,
            "headline": data.get("executive_narrative"),
            "kpis": summary,
            "priority_signals": RevenueReconciliationService._priority_signals(data),
            "next_actions": RevenueReconciliationService._next_actions(data),
        }

    @staticmethod
    def _priority_signals(data: dict[str, Any]) -> list[dict[str, Any]]:
        summary = data.get("summary", {})
        signals = []
        if data.get("status") == "AWAITING_SELLER_CENTRAL_DATA":
            signals.append({"priority": "HIGH", "signal": "Seller Central data required", "action": "Run SP-API Sales & Traffic pipeline."})
            return signals
        dep = summary.get("advertising_dependency")
        if dep == "HIGH":
            signals.append({"priority": "HIGH", "signal": "High advertising dependency", "action": "Review listing conversion and organic ranking before increasing ad spend."})
        elif dep == "LOW":
            signals.append({"priority": "MEDIUM", "signal": "Strong organic contribution", "action": "Consider scaling profitable campaigns that support organic growth."})
        tacos = summary.get("tacos")
        if isinstance(tacos, (int, float)) and tacos > 0.18:
            signals.append({"priority": "MEDIUM", "signal": "High TACOS", "action": "Focus on profit leaks, wasted spend, and listing conversion."})
        return signals or [{"priority": "LOW", "signal": "Revenue mix stable", "action": "Continue monitoring organic vs paid trend."}]

    @staticmethod
    def _next_actions(data: dict[str, Any]) -> list[str]:
        if data.get("status") == "AWAITING_SELLER_CENTRAL_DATA":
            return ["Run POST /business-os/sp-api/automation/nightly/run", "Then recheck GET /business-os/revenue/organic-vs-paid"]
        return [
            "Compare organic ratio against paid ratio in Mission Control.",
            "Review most ad-dependent products before increasing budgets.",
            "Use Product 360 to inspect products with weak organic contribution.",
        ]

    @staticmethod
    def _narrative(total: float, paid: float, organic: float, ad_spend: float, seller_status: str | None) -> str:
        if seller_status == "AWAITING_SELLER_CENTRAL_DATA" or total <= 0:
            return "Seller Central Sales & Traffic data is required before organic versus paid revenue can be calculated."
        organic_ratio = RevenueReconciliationService._ratio(organic, total)
        paid_ratio = RevenueReconciliationService._ratio(paid, total)
        tacos = RevenueReconciliationService._ratio(ad_spend, total)
        return f"Total revenue is {total:.2f}; organic revenue is {organic:.2f} ({organic_ratio}), paid-attributed revenue is {paid:.2f} ({paid_ratio}), and TACOS is {tacos}."

    @staticmethod
    def _dependency_label(paid: float, total: float) -> str:
        ratio = paid / total if total else 0
        if ratio >= 0.50:
            return "HIGH"
        if ratio >= 0.25:
            return "MEDIUM"
        if total > 0:
            return "LOW"
        return "UNKNOWN"

    @staticmethod
    def _ratio(numerator: float, denominator: float):
        return round(numerator / denominator, 4) if denominator else None

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value if value is not None else default)
        except Exception:
            return default
