"""Business OS v8.6 — Revenue Intelligence Engine.

This engine reconciles:
- Seller Central total revenue from SP-API Sales & Traffic reports
- Amazon Advertising paid attributed revenue and ad spend

Organic revenue is estimated as: total revenue - paid attributed revenue.
When SP-API/Seller Central rows are not yet present, the engine returns a clear
AWAITING_SELLER_CENTRAL_DATA status instead of pretending organic data exists.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from database import SessionLocal
from models import CampaignDailyDetail, DailyDashboard, SellerCentralSalesTraffic
from business_data_context import resolve_data_context, apply_date_context, apply_marketplace_context
from revenue.models import RevenueBreakdown, RevenueSignals


class RevenueIntelligenceEngine:
    version = "8.6"

    @staticmethod
    def sp_api_status() -> dict[str, Any]:
        return {
            "status": "READY_FOR_CONNECTION",
            "version": RevenueIntelligenceEngine.version,
            "api": "Amazon Selling Partner API (SP-API)",
            "report_type": "GET_SALES_AND_TRAFFIC_REPORT",
            "required_data": [
                "date",
                "asin or sku",
                "ordered_product_sales",
                "units_ordered",
                "total_order_items",
                "sessions",
                "page_views",
                "buy_box_percentage",
            ],
            "current_mode": "database_reconciliation_ready",
            "message": "Revenue Intelligence is installed. Populate seller_central_sales_traffic from SP-API Sales & Traffic reports to calculate organic sales.",
        }

    @staticmethod
    def diagnostics() -> dict[str, Any]:
        db = SessionLocal()
        try:
            seller_rows = db.query(SellerCentralSalesTraffic).count()
            ad_rows = db.query(CampaignDailyDetail).count()
            dashboard_rows = db.query(DailyDashboard).count()
            checks = {
                "database": "OK",
                "seller_central_sales_traffic_table": "OK",
                "amazon_ads_campaign_details": "OK",
                "daily_dashboards": "OK",
                "sp_api_report_ingestion": "READY" if seller_rows > 0 else "AWAITING_DATA",
            }
            return {
                "status": "OK",
                "version": RevenueIntelligenceEngine.version,
                "checks": checks,
                "counts": {
                    "seller_central_sales_traffic_rows": seller_rows,
                    "campaign_daily_detail_rows": ad_rows,
                    "daily_dashboard_rows": dashboard_rows,
                },
                "capabilities": [
                    "paid_vs_organic_revenue",
                    "organic_ratio",
                    "paid_ratio",
                    "tacos_from_total_revenue",
                    "advertising_dependency",
                    "revenue_confidence",
                    "multi_channel_ready_model",
                ],
            }
        except Exception as exc:
            return {"status": "ERROR", "version": RevenueIntelligenceEngine.version, "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def summary(window: str = "latest", country_code: str | None = None, profile_id: str | None = None) -> dict[str, Any]:
        marketplaces = RevenueIntelligenceEngine.marketplaces(window=window, country_code=country_code, profile_id=profile_id)
        products = RevenueIntelligenceEngine.products(window=window, country_code=country_code, profile_id=profile_id, limit=25)
        combined = marketplaces.get("combined", {}) if isinstance(marketplaces, dict) else {}
        return {
            "status": marketplaces.get("status", "OK") if isinstance(marketplaces, dict) else "OK",
            "version": RevenueIntelligenceEngine.version,
            "data_context": marketplaces.get("data_context") if isinstance(marketplaces, dict) else None,
            "combined": combined,
            "top_organic_strength": products.get("top_organic_strength", []) if isinstance(products, dict) else [],
            "most_ad_dependent": products.get("most_ad_dependent", []) if isinstance(products, dict) else [],
            "seller_central_data_status": marketplaces.get("seller_central_data_status") if isinstance(marketplaces, dict) else "UNKNOWN",
            "narrative": RevenueIntelligenceEngine._narrative(combined, marketplaces.get("seller_central_data_status") if isinstance(marketplaces, dict) else None),
        }

    @staticmethod
    def marketplaces(window: str = "latest", country_code: str | None = None, profile_id: str | None = None) -> dict[str, Any]:
        context = resolve_data_context(window=window, country_code=country_code, profile_id=profile_id)
        db = SessionLocal()
        try:
            seller_rows = RevenueIntelligenceEngine._seller_rows(db, context)
            ad_rows = RevenueIntelligenceEngine._ad_dashboard_rows(db, context)
            seller_by_market = defaultdict(lambda: RevenueIntelligenceEngine._empty_seller_bucket())
            for row in seller_rows:
                key = RevenueIntelligenceEngine._market_key(row.country_code, row.marketplace, row.currency)
                bucket = seller_by_market[key]
                RevenueIntelligenceEngine._add_seller(bucket, row)

            ads_by_market = defaultdict(lambda: RevenueIntelligenceEngine._empty_ad_bucket())
            for row in ad_rows:
                key = RevenueIntelligenceEngine._market_key(row.country_code, row.marketplace, row.currency)
                bucket = ads_by_market[key]
                RevenueIntelligenceEngine._add_ad(bucket, row)

            keys = sorted(set(seller_by_market.keys()) | set(ads_by_market.keys()))
            items = []
            for key in keys:
                seller = seller_by_market.get(key, RevenueIntelligenceEngine._empty_seller_bucket())
                ads = ads_by_market.get(key, RevenueIntelligenceEngine._empty_ad_bucket())
                country, marketplace, currency = key
                item = RevenueIntelligenceEngine._breakdown(
                    identity={
                        "country_code": country,
                        "marketplace": marketplace,
                        "currency": currency,
                        "label": f"{country or 'Unknown'} / {marketplace or 'unknown'}",
                        "channel": "amazon",
                    },
                    seller=seller,
                    ads=ads,
                )
                items.append(item)

            combined = RevenueIntelligenceEngine._combine(items)
            seller_status = "OK" if seller_rows else "AWAITING_SELLER_CENTRAL_DATA"
            return {
                "status": "OK",
                "version": RevenueIntelligenceEngine.version,
                "data_context": context,
                "seller_central_data_status": seller_status,
                "count": len(items),
                "combined": combined,
                "marketplaces": items,
                "narrative": RevenueIntelligenceEngine._narrative(combined, seller_status),
            }
        finally:
            db.close()

    @staticmethod
    def products(window: str = "latest", country_code: str | None = None, profile_id: str | None = None, limit: int = 50) -> dict[str, Any]:
        context = resolve_data_context(window=window, country_code=country_code, profile_id=profile_id)
        db = SessionLocal()
        try:
            seller_rows = RevenueIntelligenceEngine._seller_rows(db, context)
            # Advertising reports currently do not provide reliable ASIN/SKU-level paid sales in this app.
            # Product rows still expose organic/total metrics and declare paid revenue confidence accordingly.
            seller_by_product = defaultdict(lambda: RevenueIntelligenceEngine._empty_seller_bucket())
            for row in seller_rows:
                key = (row.asin or "unknown", row.sku or "", row.country_code or "", row.marketplace or "", row.currency or "")
                bucket = seller_by_product[key]
                RevenueIntelligenceEngine._add_seller(bucket, row)

            items = []
            for key, seller in seller_by_product.items():
                asin, sku, country, marketplace, currency = key
                item = RevenueIntelligenceEngine._breakdown(
                    identity={
                        "asin": asin,
                        "sku": sku or None,
                        "title": seller.get("title"),
                        "country_code": country,
                        "marketplace": marketplace,
                        "currency": currency,
                        "channel": "amazon",
                    },
                    seller=seller,
                    ads=RevenueIntelligenceEngine._empty_ad_bucket(),
                    product_level=True,
                )
                items.append(item)

            items.sort(key=lambda item: (item.get("organic_revenue") or 0, item.get("total_revenue") or 0), reverse=True)
            limited = items[: max(1, min(limit, 250))]
            combined = RevenueIntelligenceEngine._combine(items)
            seller_status = "OK" if seller_rows else "AWAITING_SELLER_CENTRAL_DATA"
            return {
                "status": "OK",
                "version": RevenueIntelligenceEngine.version,
                "data_context": context,
                "seller_central_data_status": seller_status,
                "count": len(limited),
                "combined": combined,
                "products": limited,
                "top_organic_strength": [i for i in limited if i.get("organic_momentum") in {"STRONG", "BALANCED"}][:10],
                "most_ad_dependent": sorted(limited, key=lambda i: i.get("paid_ratio") or 0, reverse=True)[:10],
                "note": "Product-level paid revenue requires ASIN/SKU attribution from ads reports. Until then, product paid revenue remains conservative.",
            }
        finally:
            db.close()

    @staticmethod
    def paid_vs_organic(window: str = "latest", country_code: str | None = None, profile_id: str | None = None) -> dict[str, Any]:
        return RevenueIntelligenceEngine.marketplaces(window=window, country_code=country_code, profile_id=profile_id)

    @staticmethod
    def _seller_rows(db, context: dict[str, Any]):
        query = db.query(SellerCentralSalesTraffic)
        query = apply_date_context(query, SellerCentralSalesTraffic, context)
        query = apply_marketplace_context(query, SellerCentralSalesTraffic, context)
        return query.all()

    @staticmethod
    def _ad_dashboard_rows(db, context: dict[str, Any]):
        query = db.query(DailyDashboard).filter(DailyDashboard.channel == "amazon_ads")
        query = apply_date_context(query, DailyDashboard, context)
        query = apply_marketplace_context(query, DailyDashboard, context)
        return query.all()

    @staticmethod
    def _empty_seller_bucket() -> dict[str, Any]:
        return {"total_revenue": 0.0, "orders": 0, "units_ordered": 0, "sessions": 0, "page_views": 0, "buy_box_sum": 0.0, "buy_box_count": 0, "title": None}

    @staticmethod
    def _empty_ad_bucket() -> dict[str, Any]:
        return {"paid_revenue": 0.0, "ad_spend": 0.0, "orders": 0, "clicks": 0, "impressions": 0}

    @staticmethod
    def _add_seller(bucket: dict[str, Any], row: SellerCentralSalesTraffic) -> None:
        bucket["total_revenue"] += RevenueIntelligenceEngine._safe_float(row.ordered_product_sales)
        bucket["orders"] += RevenueIntelligenceEngine._safe_int(row.total_order_items)
        bucket["units_ordered"] += RevenueIntelligenceEngine._safe_int(row.units_ordered)
        bucket["sessions"] += RevenueIntelligenceEngine._safe_int(row.sessions)
        bucket["page_views"] += RevenueIntelligenceEngine._safe_int(row.page_views)
        if row.buy_box_percentage is not None:
            bucket["buy_box_sum"] += RevenueIntelligenceEngine._safe_float(row.buy_box_percentage)
            bucket["buy_box_count"] += 1
        if row.title and not bucket.get("title"):
            bucket["title"] = row.title

    @staticmethod
    def _add_ad(bucket: dict[str, Any], row: DailyDashboard) -> None:
        bucket["paid_revenue"] += RevenueIntelligenceEngine._safe_float(row.sales)
        bucket["ad_spend"] += RevenueIntelligenceEngine._safe_float(row.spend)
        bucket["orders"] += RevenueIntelligenceEngine._safe_int(row.orders)
        bucket["clicks"] += RevenueIntelligenceEngine._safe_int(row.clicks)
        bucket["impressions"] += RevenueIntelligenceEngine._safe_int(row.impressions)

    @staticmethod
    def _breakdown(identity: dict[str, Any], seller: dict[str, Any], ads: dict[str, Any], product_level: bool = False) -> dict[str, Any]:
        total = RevenueIntelligenceEngine._safe_float(seller.get("total_revenue"))
        paid = RevenueIntelligenceEngine._safe_float(ads.get("paid_revenue"))
        spend = RevenueIntelligenceEngine._safe_float(ads.get("ad_spend"))
        if total <= 0:
            organic = 0.0
            confidence = 15 if paid or spend else 0
            basis = "awaiting_seller_central_data"
        else:
            organic = max(total - paid, 0.0)
            # Marketplace level can reconcile Ads dashboard to Seller Central. Product level awaits ads ASIN mapping.
            confidence = 85 if not product_level and paid <= total * 1.25 else 65
            if product_level:
                confidence = 60
            basis = "seller_central_minus_paid_ads" if not product_level else "seller_central_total_product_revenue"
        breakdown = RevenueBreakdown(
            total_revenue=total,
            paid_revenue=paid,
            organic_revenue=organic,
            ad_spend=spend,
            orders=RevenueIntelligenceEngine._safe_int(seller.get("orders") or ads.get("orders")),
            units_ordered=RevenueIntelligenceEngine._safe_int(seller.get("units_ordered")),
            sessions=RevenueIntelligenceEngine._safe_int(seller.get("sessions")),
            currency=identity.get("currency"),
            confidence=confidence,
            basis=basis,
        ).to_dict()
        buy_box_count = RevenueIntelligenceEngine._safe_int(seller.get("buy_box_count"))
        buy_box = (RevenueIntelligenceEngine._safe_float(seller.get("buy_box_sum")) / buy_box_count) if buy_box_count else None
        result = {**identity, **breakdown}
        result["page_views"] = RevenueIntelligenceEngine._safe_int(seller.get("page_views"))
        result["buy_box_percentage"] = round(buy_box, 4) if buy_box is not None else None
        result["paid_orders"] = RevenueIntelligenceEngine._safe_int(ads.get("orders"))
        result["ad_clicks"] = RevenueIntelligenceEngine._safe_int(ads.get("clicks"))
        result["ad_impressions"] = RevenueIntelligenceEngine._safe_int(ads.get("impressions"))
        result["revenue_recommendation"] = RevenueSignals.recommendation(result)
        return result

    @staticmethod
    def _combine(items: list[dict[str, Any]]) -> dict[str, Any]:
        total = sum(RevenueIntelligenceEngine._safe_float(item.get("total_revenue")) for item in items)
        paid = sum(RevenueIntelligenceEngine._safe_float(item.get("paid_revenue")) for item in items)
        organic = sum(RevenueIntelligenceEngine._safe_float(item.get("organic_revenue")) for item in items)
        spend = sum(RevenueIntelligenceEngine._safe_float(item.get("ad_spend")) for item in items)
        orders = sum(RevenueIntelligenceEngine._safe_int(item.get("orders")) for item in items)
        units = sum(RevenueIntelligenceEngine._safe_int(item.get("units_ordered")) for item in items)
        sessions = sum(RevenueIntelligenceEngine._safe_int(item.get("sessions")) for item in items)
        confidence_values = [RevenueIntelligenceEngine._safe_int(item.get("confidence")) for item in items if item.get("confidence") is not None]
        confidence = round(sum(confidence_values) / len(confidence_values)) if confidence_values else 0
        return RevenueBreakdown(total, paid, organic, spend, orders, units, sessions, None, confidence, "combined").to_dict()

    @staticmethod
    def _market_key(country_code: str | None, marketplace: str | None, currency: str | None) -> tuple[str, str, str]:
        return (str(country_code or "").upper(), str(marketplace or ""), str(currency or ""))

    @staticmethod
    def _narrative(combined: dict[str, Any], seller_status: str | None) -> str:
        if seller_status == "AWAITING_SELLER_CENTRAL_DATA":
            return "Revenue Intelligence is installed, but Seller Central Sales & Traffic data is required before organic versus paid revenue can be calculated."
        total = RevenueIntelligenceEngine._safe_float(combined.get("total_revenue"))
        organic_ratio = combined.get("organic_ratio")
        paid_ratio = combined.get("paid_ratio")
        tacos = combined.get("tacos")
        if total <= 0:
            return "Revenue Intelligence did not find total Seller Central revenue for the selected window."
        return f"Total revenue is {total:.2f}; organic ratio is {organic_ratio}, paid ratio is {paid_ratio}, and TACOS is {tacos}."

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
