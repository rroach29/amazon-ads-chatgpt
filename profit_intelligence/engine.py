"""Business OS v8.5 — Profit Intelligence Engine.

This module converts ad revenue and spend into business-oriented profit signals.
It is intentionally additive and heuristic-safe: it does not require Seller
Central fee exports yet, but it is structured so real SKU/ASIN economics can be
plugged in later.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from database import SessionLocal
from models import CampaignDailyDetail, DailyDashboard, Product
from business_data_context import resolve_data_context, apply_date_context, apply_marketplace_context


@dataclass
class ProfitAssumptions:
    """Fallback economics used when product-level values are unavailable."""

    default_cogs_percent: float = 0.12
    default_amazon_fee_percent: float = 0.15
    default_shipping_percent: float = 0.08
    default_variable_cost_percent: float = 0.35
    basis: str = "heuristic_default"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProductEconomics:
    """Resolved economics for a product, campaign, or marketplace aggregate."""

    cogs_percent: float
    amazon_fee_percent: float
    shipping_percent: float
    variable_cost_percent: float
    basis: str = "heuristic_default"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProfitIntelligenceEngine:
    version = "8.5"

    @staticmethod
    def assumptions() -> dict[str, Any]:
        return {
            "status": "OK",
            "version": ProfitIntelligenceEngine.version,
            "assumptions": ProfitAssumptions().to_dict(),
            "note": "These are conservative fallback assumptions until Seller Central fee/order economics or explicit product economics are connected.",
        }

    @staticmethod
    def diagnostics() -> dict[str, Any]:
        db = SessionLocal()
        try:
            product_count = db.query(Product).count()
            campaign_rows = db.query(CampaignDailyDetail).count()
            dashboard_rows = db.query(DailyDashboard).count()
            return {
                "status": "OK",
                "version": ProfitIntelligenceEngine.version,
                "checks": {
                    "database": "OK",
                    "product_table": "OK",
                    "campaign_daily_details": "OK",
                    "daily_dashboards": "OK",
                },
                "counts": {
                    "products": product_count,
                    "campaign_daily_details": campaign_rows,
                    "daily_dashboards": dashboard_rows,
                },
                "profit_mode": "estimated_until_real_fee_data_available",
            }
        except Exception as exc:  # pragma: no cover - runtime diagnostics
            return {"status": "ERROR", "version": ProfitIntelligenceEngine.version, "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def marketplace_summary(window: str = "latest", country_code: str | None = None, profile_id: str | None = None) -> dict[str, Any]:
        context = resolve_data_context(window=window, country_code=country_code, profile_id=profile_id)
        db = SessionLocal()
        try:
            query = db.query(DailyDashboard).filter(DailyDashboard.channel == "amazon_ads")
            query = apply_date_context(query, DailyDashboard, context)
            query = apply_marketplace_context(query, DailyDashboard, context)
            rows = query.order_by(DailyDashboard.sales.desc()).all()

            items = []
            for row in rows:
                economics = ProfitIntelligenceEngine._economics_for_marketplace(row.country_code, row.marketplace)
                items.append(ProfitIntelligenceEngine._profit_from_metrics(
                    sales=ProfitIntelligenceEngine._safe_float(row.sales),
                    spend=ProfitIntelligenceEngine._safe_float(row.spend),
                    orders=ProfitIntelligenceEngine._safe_int(row.orders),
                    clicks=ProfitIntelligenceEngine._safe_int(row.clicks),
                    impressions=ProfitIntelligenceEngine._safe_int(row.impressions),
                    currency=row.currency,
                    economics=economics,
                    identity={
                        "date": str(row.date) if row.date else None,
                        "profile_id": row.profile_id,
                        "country_code": row.country_code,
                        "marketplace": row.marketplace,
                        "label": f"{row.country_code or 'Unknown'} / {row.marketplace or 'unknown'}",
                    },
                ))

            combined = ProfitIntelligenceEngine._combine(items)
            return {
                "status": "OK",
                "version": ProfitIntelligenceEngine.version,
                "data_context": context,
                "count": len(items),
                "combined": combined,
                "marketplaces": items,
                "narrative": ProfitIntelligenceEngine._summary_narrative(combined),
            }
        finally:
            db.close()

    @staticmethod
    def campaign_profit(window: str = "latest", country_code: str | None = None, profile_id: str | None = None, limit: int = 50) -> dict[str, Any]:
        context = resolve_data_context(window=window, country_code=country_code, profile_id=profile_id)
        db = SessionLocal()
        try:
            query = db.query(CampaignDailyDetail).filter(CampaignDailyDetail.channel == "amazon_ads")
            query = apply_date_context(query, CampaignDailyDetail, context)
            query = apply_marketplace_context(query, CampaignDailyDetail, context)
            rows = query.order_by(CampaignDailyDetail.sales.desc(), CampaignDailyDetail.spend.desc()).limit(max(1, min(limit, 250))).all()

            items = []
            for row in rows:
                economics = ProfitIntelligenceEngine._economics_for_campaign(row.campaign_name, row.country_code, row.marketplace)
                item = ProfitIntelligenceEngine._profit_from_metrics(
                    sales=ProfitIntelligenceEngine._safe_float(row.sales),
                    spend=ProfitIntelligenceEngine._safe_float(row.spend),
                    orders=ProfitIntelligenceEngine._safe_int(row.orders),
                    clicks=ProfitIntelligenceEngine._safe_int(row.clicks),
                    impressions=ProfitIntelligenceEngine._safe_int(row.impressions),
                    currency=row.currency,
                    economics=economics,
                    identity={
                        "date": str(row.date) if row.date else None,
                        "campaign_id": str(row.campaign_id or ""),
                        "campaign_name": row.campaign_name,
                        "campaign_status": row.campaign_status,
                        "profile_id": row.profile_id,
                        "country_code": row.country_code,
                        "marketplace": row.marketplace,
                    },
                )
                item["profit_recommendation"] = ProfitIntelligenceEngine._profit_recommendation(item)
                items.append(item)

            items.sort(key=lambda item: item.get("contribution_profit", 0), reverse=True)
            combined = ProfitIntelligenceEngine._combine(items)
            return {
                "status": "OK",
                "version": ProfitIntelligenceEngine.version,
                "data_context": context,
                "count": len(items),
                "combined": combined,
                "campaigns": items,
                "top_profitable_campaigns": [item for item in items if item.get("contribution_profit", 0) > 0][:10],
                "profit_leaks": [item for item in sorted(items, key=lambda item: item.get("contribution_profit", 0)) if item.get("contribution_profit", 0) < 0][:10],
                "narrative": ProfitIntelligenceEngine._summary_narrative(combined),
            }
        finally:
            db.close()

    @staticmethod
    def executive_summary(window: str = "latest", country_code: str | None = None, profile_id: str | None = None) -> dict[str, Any]:
        marketplace = ProfitIntelligenceEngine.marketplace_summary(window=window, country_code=country_code, profile_id=profile_id)
        campaigns = ProfitIntelligenceEngine.campaign_profit(window=window, country_code=country_code, profile_id=profile_id, limit=25)
        combined = marketplace.get("combined", {}) if isinstance(marketplace, dict) else {}
        profit_leaks = campaigns.get("profit_leaks", []) if isinstance(campaigns, dict) else []
        winners = campaigns.get("top_profitable_campaigns", []) if isinstance(campaigns, dict) else []
        return {
            "status": "OK",
            "version": ProfitIntelligenceEngine.version,
            "data_context": marketplace.get("data_context"),
            "profit_summary": combined,
            "top_profit_drivers": winners[:5],
            "top_profit_leaks": profit_leaks[:5],
            "operating_note": "Profit is estimated from ad sales, ad spend, and fallback/product economics. Connect Seller Central order economics later for actual net profit.",
            "narrative": ProfitIntelligenceEngine._summary_narrative(combined),
        }

    @staticmethod
    def _economics_for_marketplace(country_code: str | None, marketplace: str | None) -> ProductEconomics:
        assumptions = ProfitAssumptions()
        return ProductEconomics(
            cogs_percent=assumptions.default_cogs_percent,
            amazon_fee_percent=assumptions.default_amazon_fee_percent,
            shipping_percent=assumptions.default_shipping_percent,
            variable_cost_percent=assumptions.default_variable_cost_percent,
            basis="marketplace_fallback",
        )

    @staticmethod
    def _economics_for_campaign(campaign_name: str | None, country_code: str | None, marketplace: str | None) -> ProductEconomics:
        # Current reports do not reliably map campaign -> ASIN/SKU yet. Keep the
        # resolver isolated so Knowledge Graph/Product Catalog mapping can replace
        # this heuristic in a future release without touching endpoint contracts.
        return ProfitIntelligenceEngine._economics_for_marketplace(country_code, marketplace)

    @staticmethod
    def _profit_from_metrics(
        sales: float,
        spend: float,
        orders: int,
        clicks: int,
        impressions: int,
        currency: str | None,
        economics: ProductEconomics,
        identity: dict[str, Any],
    ) -> dict[str, Any]:
        cogs = sales * economics.cogs_percent
        amazon_fees = sales * economics.amazon_fee_percent
        shipping = sales * economics.shipping_percent
        gross_profit = sales - cogs - amazon_fees - shipping
        contribution_profit = gross_profit - spend
        contribution_margin = contribution_profit / sales if sales else None
        gross_margin = gross_profit / sales if sales else None
        tacos = spend / sales if sales else None
        return {
            **identity,
            "currency": currency,
            "sales": round(sales, 2),
            "ad_spend": round(spend, 2),
            "orders": orders,
            "clicks": clicks,
            "impressions": impressions,
            "estimated_cogs": round(cogs, 2),
            "estimated_amazon_fees": round(amazon_fees, 2),
            "estimated_shipping": round(shipping, 2),
            "estimated_gross_profit": round(gross_profit, 2),
            "contribution_profit": round(contribution_profit, 2),
            "gross_margin": round(gross_margin, 4) if gross_margin is not None else None,
            "contribution_margin": round(contribution_margin, 4) if contribution_margin is not None else None,
            "tacos": round(tacos, 4) if tacos is not None else None,
            "profit_score": ProfitIntelligenceEngine._profit_score(contribution_profit, contribution_margin, sales, spend),
            "economics": economics.to_dict(),
        }

    @staticmethod
    def _combine(items: list[dict[str, Any]]) -> dict[str, Any]:
        sales = sum(ProfitIntelligenceEngine._safe_float(item.get("sales")) for item in items)
        spend = sum(ProfitIntelligenceEngine._safe_float(item.get("ad_spend")) for item in items)
        cogs = sum(ProfitIntelligenceEngine._safe_float(item.get("estimated_cogs")) for item in items)
        fees = sum(ProfitIntelligenceEngine._safe_float(item.get("estimated_amazon_fees")) for item in items)
        shipping = sum(ProfitIntelligenceEngine._safe_float(item.get("estimated_shipping")) for item in items)
        gross_profit = sum(ProfitIntelligenceEngine._safe_float(item.get("estimated_gross_profit")) for item in items)
        contribution_profit = sum(ProfitIntelligenceEngine._safe_float(item.get("contribution_profit")) for item in items)
        orders = sum(ProfitIntelligenceEngine._safe_int(item.get("orders")) for item in items)
        return {
            "sales": round(sales, 2),
            "ad_spend": round(spend, 2),
            "orders": orders,
            "estimated_cogs": round(cogs, 2),
            "estimated_amazon_fees": round(fees, 2),
            "estimated_shipping": round(shipping, 2),
            "estimated_gross_profit": round(gross_profit, 2),
            "contribution_profit": round(contribution_profit, 2),
            "gross_margin": round(gross_profit / sales, 4) if sales else None,
            "contribution_margin": round(contribution_profit / sales, 4) if sales else None,
            "tacos": round(spend / sales, 4) if sales else None,
            "profit_score": ProfitIntelligenceEngine._profit_score(contribution_profit, contribution_profit / sales if sales else None, sales, spend),
        }

    @staticmethod
    def _profit_score(contribution_profit: float, contribution_margin: float | None, sales: float, spend: float) -> int:
        margin_component = 0 if contribution_margin is None else max(-30, min(contribution_margin * 100, 60))
        profit_component = max(-25, min(contribution_profit / 10, 30))
        scale_component = max(0, min(sales / 50, 10))
        waste_penalty = 10 if sales <= 0 and spend > 0 else 0
        score = 50 + margin_component + profit_component + scale_component - waste_penalty
        return int(max(0, min(round(score), 100)))

    @staticmethod
    def _profit_recommendation(item: dict[str, Any]) -> dict[str, Any]:
        profit = ProfitIntelligenceEngine._safe_float(item.get("contribution_profit"))
        sales = ProfitIntelligenceEngine._safe_float(item.get("sales"))
        spend = ProfitIntelligenceEngine._safe_float(item.get("ad_spend"))
        tacos = item.get("tacos")
        if sales <= 0 and spend > 0:
            return {"signal": "PROFIT_LEAK", "message": "Campaign spent without attributed sales. Prioritize waste reduction before scaling."}
        if profit > 0 and tacos is not None and tacos < 0.20:
            return {"signal": "PROFIT_DRIVER", "message": "Campaign appears contribution-positive with room to evaluate careful scaling."}
        if profit < 0:
            return {"signal": "NEGATIVE_CONTRIBUTION", "message": "Estimated contribution profit is negative. Review bids, budgets, targeting, and listing conversion."}
        return {"signal": "MONITOR", "message": "No urgent profit action detected from current data."}

    @staticmethod
    def _summary_narrative(combined: dict[str, Any]) -> str:
        profit = ProfitIntelligenceEngine._safe_float(combined.get("contribution_profit"))
        sales = ProfitIntelligenceEngine._safe_float(combined.get("sales"))
        spend = ProfitIntelligenceEngine._safe_float(combined.get("ad_spend"))
        if sales <= 0 and spend > 0:
            return "Ad spend is active but attributed sales are zero in the selected window; profit intelligence recommends waste review first."
        if profit > 0:
            return f"Estimated contribution profit is positive at {profit:.2f} on {sales:.2f} sales."
        if profit < 0:
            return f"Estimated contribution profit is negative at {profit:.2f}; focus on profit leaks before scaling."
        return "Profit intelligence is available, but the selected window has limited sales/spend signal."

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value if value is not None else default)
        except Exception:
            return default

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value if value is not None else default)
        except Exception:
            return default
