"""Business OS v9.0.8 — Attribution-aware revenue reconciliation.

Important correction:
Amazon Ads campaign reports currently map `sales7d` to CampaignDailyDetail.sales
and `purchases7d` to CampaignDailyDetail.orders.

Those are 7-day click-attributed advertising metrics, not same-day Seller Central
revenue. Therefore they must NOT be subtracted from Seller Central daily revenue
to calculate organic revenue.

This service now reports:
- Seller Central total revenue/orders as the source of truth for daily revenue.
- Amazon Ads spend as same-day spend.
- Amazon Ads attributed sales/orders as attribution-window metrics.
- Organic revenue as UNKNOWN until a true same-day paid revenue source is added.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

from database import SessionLocal
from models import CampaignDailyDetail, DailyDashboard, SPAPIReportJob, SellerCentralSalesTraffic


class RevenueReconciliationService:
    version = "9.0.8"

    @staticmethod
    def organic_vs_paid(
        window: str = "latest",
        country_code: str | None = None,
        profile_id: str | None = None,
        debug: bool = False,
    ) -> dict[str, Any]:
        db = SessionLocal()
        try:
            alignment = RevenueReconciliationService._alignment(db, country_code=country_code, profile_id=profile_id)
            aligned_date = alignment.get("aligned_date")

            if not aligned_date:
                return RevenueReconciliationService._empty_response(alignment, debug=debug)

            seller_rows = RevenueReconciliationService._seller_rows(db, aligned_date, country_code)
            ad_rows = RevenueReconciliationService._campaign_rows(db, aligned_date, country_code, profile_id)

            seller_by_market = defaultdict(lambda: RevenueReconciliationService._empty_seller_bucket())
            for row in seller_rows:
                key = RevenueReconciliationService._canonical_market_key(row.country_code, row.marketplace, row.currency)
                # Ignore unknown aggregate Seller Central rows if marketplace rows are present.
                if key[0] == "UNKNOWN":
                    continue
                RevenueReconciliationService._add_seller(seller_by_market[key], row)

            ads_by_market = defaultdict(lambda: RevenueReconciliationService._empty_ad_bucket())
            for row in ad_rows:
                key = RevenueReconciliationService._canonical_market_key(row.country_code, row.marketplace, row.currency)
                if key[0] == "UNKNOWN":
                    continue
                RevenueReconciliationService._add_ad_attribution(ads_by_market[key], row)

            keys = sorted(set(seller_by_market.keys()) | set(ads_by_market.keys()))
            marketplaces = [
                RevenueReconciliationService._marketplace_breakdown(
                    country=key[0],
                    marketplace=key[1],
                    currency=key[2],
                    seller=seller_by_market.get(key, RevenueReconciliationService._empty_seller_bucket()),
                    ads=ads_by_market.get(key, RevenueReconciliationService._empty_ad_bucket()),
                )
                for key in keys
            ]

            summary = RevenueReconciliationService._combine(marketplaces)
            status = "OK" if summary["total_revenue"] > 0 else "AWAITING_SELLER_CENTRAL_DATA"

            response = {
                "status": status,
                "version": RevenueReconciliationService.version,
                "headline": RevenueReconciliationService._headline(summary, alignment),
                "data_freshness": alignment,
                "seller_central_pipeline_status": RevenueReconciliationService._seller_pipeline_status(db),
                "kpis": {
                    **summary,
                    "confidence": 82 if summary["total_revenue"] > 0 else 0,
                    "confidence_reason": {
                        "level": "MEDIUM" if summary["total_revenue"] > 0 else "LOW",
                        "reason": "Seller Central daily revenue is available. Organic-vs-paid revenue is not calculated because Amazon Ads sales are 7-day attributed metrics, not same-day paid revenue.",
                        "data_freshness": alignment,
                        "ads_attribution_warning": RevenueReconciliationService._ads_attribution_warning(),
                    },
                },
                "marketplaces": marketplaces,
                "priority_signals": RevenueReconciliationService._priority_signals(summary, alignment),
                "next_actions": RevenueReconciliationService._next_actions(),
                "data_quality_warnings": [
                    RevenueReconciliationService._ads_attribution_warning()
                ],
                "reconciliation_source": {
                    "seller_central": "seller_central_sales_traffic exact aligned_date; daily total revenue/orders",
                    "amazon_ads": "campaign_daily_details exact aligned_date; sales field is sales7d attribution-window metric",
                    "root_fix": "v9.0.8 stops subtracting Amazon Ads sales7d from Seller Central same-day revenue.",
                },
            }

            if debug:
                response["debug"] = {
                    "seller_rows_included": len(seller_rows),
                    "campaign_rows_included": len(ad_rows),
                    "ads_metric_mapping": {
                        "CampaignDailyDetail.sales": "Amazon Ads sales7d",
                        "CampaignDailyDetail.orders": "Amazon Ads purchases7d",
                        "valid_for_campaign_performance": True,
                        "valid_for_same_day_revenue_reconciliation": False,
                    },
                    "seller_rows": [RevenueReconciliationService._seller_debug_row(row) for row in seller_rows],
                    "campaign_rows_sample": [RevenueReconciliationService._campaign_debug_row(row) for row in ad_rows[:100]],
                }

            return response
        finally:
            db.close()

    @staticmethod
    def executive_snapshot(window: str = "latest", country_code: str | None = None, profile_id: str | None = None) -> dict[str, Any]:
        data = RevenueReconciliationService.organic_vs_paid(window=window, country_code=country_code, profile_id=profile_id)
        return {
            "status": data.get("status"),
            "version": RevenueReconciliationService.version,
            "headline": data.get("headline"),
            "kpis": data.get("kpis", {}),
            "data_freshness": data.get("data_freshness"),
            "priority_signals": data.get("priority_signals", []),
            "next_actions": data.get("next_actions", []),
            "data_quality_warnings": data.get("data_quality_warnings", []),
        }

    @staticmethod
    def data_health(country_code: str | None = None, profile_id: str | None = None) -> dict[str, Any]:
        db = SessionLocal()
        try:
            return {
                "status": "OK",
                "version": RevenueReconciliationService.version,
                "data_freshness": RevenueReconciliationService._alignment(db, country_code, profile_id),
                "row_counts": {
                    "seller_central_sales_traffic": db.query(SellerCentralSalesTraffic).count(),
                    "campaign_daily_details_amazon_ads": db.query(CampaignDailyDetail).filter(CampaignDailyDetail.channel == "amazon_ads").count(),
                    "daily_dashboards_amazon_ads": db.query(DailyDashboard).filter(DailyDashboard.channel == "amazon_ads").count(),
                },
                "seller_central_pipeline_status": RevenueReconciliationService._seller_pipeline_status(db),
                "ads_metric_warning": RevenueReconciliationService._ads_attribution_warning(),
            }
        finally:
            db.close()

    @staticmethod
    def _alignment(db, country_code: str | None = None, profile_id: str | None = None) -> dict[str, Any]:
        seller_query = db.query(SellerCentralSalesTraffic.date).filter(SellerCentralSalesTraffic.date.isnot(None))
        ads_query = db.query(CampaignDailyDetail.date).filter(CampaignDailyDetail.channel == "amazon_ads").filter(CampaignDailyDetail.date.isnot(None))
        if country_code:
            cc = country_code.upper()
            seller_query = seller_query.filter(SellerCentralSalesTraffic.country_code == cc)
            ads_query = ads_query.filter(CampaignDailyDetail.country_code == cc)
        if profile_id:
            ads_query = ads_query.filter(CampaignDailyDetail.profile_id == profile_id)

        seller_dates = {RevenueReconciliationService._date_only(r[0]) for r in seller_query.distinct().all() if r[0]}
        ads_dates = {RevenueReconciliationService._date_only(r[0]) for r in ads_query.distinct().all() if r[0]}
        seller_dates.discard(None)
        ads_dates.discard(None)

        seller_latest = max(seller_dates) if seller_dates else None
        ads_latest = max(ads_dates) if ads_dates else None
        common = seller_dates & ads_dates
        aligned_date = max(common) if common else None
        aligned = bool(aligned_date and aligned_date == seller_latest == ads_latest)
        return {
            "amazon_ads_latest_date": RevenueReconciliationService._date_str(ads_latest),
            "seller_central_latest_date": RevenueReconciliationService._date_str(seller_latest),
            "aligned_date": RevenueReconciliationService._date_str(aligned_date),
            "aligned": aligned,
            "reason": "Amazon Ads and Seller Central are aligned on the latest date." if aligned else "Amazon Ads and Seller Central data are not on the same latest date; using latest common date for combined reporting.",
        }

    @staticmethod
    def _seller_rows(db, aligned_date: str, country_code: str | None = None):
        q = db.query(SellerCentralSalesTraffic).filter(SellerCentralSalesTraffic.date == aligned_date)
        if country_code:
            q = q.filter(SellerCentralSalesTraffic.country_code == country_code.upper())
        return q.all()

    @staticmethod
    def _campaign_rows(db, aligned_date: str, country_code: str | None = None, profile_id: str | None = None):
        q = db.query(CampaignDailyDetail).filter(CampaignDailyDetail.channel == "amazon_ads").filter(CampaignDailyDetail.date == aligned_date)
        if country_code:
            q = q.filter(CampaignDailyDetail.country_code == country_code.upper())
        if profile_id:
            q = q.filter(CampaignDailyDetail.profile_id == profile_id)
        return q.all()

    @staticmethod
    def _marketplace_breakdown(country: str, marketplace: str, currency: str, seller: dict[str, Any], ads: dict[str, Any]) -> dict[str, Any]:
        total = RevenueReconciliationService._safe_float(seller.get("total_revenue"))
        spend = RevenueReconciliationService._safe_float(ads.get("ad_spend"))
        attributed = RevenueReconciliationService._safe_float(ads.get("attributed_sales_7d"))
        orders = RevenueReconciliationService._safe_int(seller.get("orders"))
        sessions = RevenueReconciliationService._safe_int(seller.get("sessions"))
        return {
            "country_code": country,
            "marketplace": marketplace,
            "currency": currency,
            "label": f"{country} / {marketplace}",
            "channel": "amazon",
            "total_revenue": round(total, 2),
            "paid_revenue": None,
            "organic_revenue": None,
            "ad_attributed_sales_7d": round(attributed, 2),
            "ad_spend": round(spend, 2),
            "orders": orders,
            "units_ordered": RevenueReconciliationService._safe_int(seller.get("units_ordered")),
            "sessions": sessions,
            "page_views": RevenueReconciliationService._safe_int(seller.get("page_views")),
            "ad_attributed_orders_7d": RevenueReconciliationService._safe_int(ads.get("attributed_orders_7d")),
            "ad_clicks": RevenueReconciliationService._safe_int(ads.get("clicks")),
            "ad_impressions": RevenueReconciliationService._safe_int(ads.get("impressions")),
            "organic_ratio": None,
            "paid_ratio": None,
            "tacos": RevenueReconciliationService._ratio(spend, total),
            "conversion_rate": RevenueReconciliationService._ratio(orders, sessions),
            "advertising_dependency": "UNKNOWN",
            "basis": "seller_central_daily_revenue_plus_ads_7d_attribution_metrics_not_subtracted",
        }

    @staticmethod
    def _combine(items):
        total = sum(RevenueReconciliationService._safe_float(i.get("total_revenue")) for i in items)
        spend = sum(RevenueReconciliationService._safe_float(i.get("ad_spend")) for i in items)
        attributed = sum(RevenueReconciliationService._safe_float(i.get("ad_attributed_sales_7d")) for i in items)
        orders = sum(RevenueReconciliationService._safe_int(i.get("orders")) for i in items)
        units = sum(RevenueReconciliationService._safe_int(i.get("units_ordered")) for i in items)
        sessions = sum(RevenueReconciliationService._safe_int(i.get("sessions")) for i in items)
        return {
            "total_revenue": round(total, 2),
            "paid_revenue": None,
            "organic_revenue": None,
            "ad_attributed_sales_7d": round(attributed, 2),
            "ad_spend": round(spend, 2),
            "orders": orders,
            "units_ordered": units,
            "sessions": sessions,
            "organic_ratio": None,
            "paid_ratio": None,
            "tacos": RevenueReconciliationService._ratio(spend, total),
            "conversion_rate": RevenueReconciliationService._ratio(orders, sessions),
            "advertising_dependency": "UNKNOWN",
            "organic_paid_reconciliation_status": "UNAVAILABLE_WITH_CURRENT_ADS_ATTRIBUTION_WINDOW",
        }

    @staticmethod
    def _headline(summary, alignment):
        if summary.get("total_revenue", 0) <= 0:
            return "Seller Central revenue is not available for the aligned date."
        return (
            f"Total Seller Central revenue for {alignment.get('aligned_date')} is {summary['total_revenue']:.2f}. "
            f"Amazon Ads attributed sales are {summary.get('ad_attributed_sales_7d'):.2f} using the current 7-day attribution metric, "
            "so organic versus paid revenue is not calculated from this field."
        )

    @staticmethod
    def _priority_signals(summary, alignment):
        signals = []
        if not alignment.get("aligned"):
            signals.append({"priority": "MEDIUM", "signal": "Data sources not fully aligned", "action": f"Using latest common date {alignment.get('aligned_date')} for combined reporting."})
        signals.append({"priority": "HIGH", "signal": "Ads attribution mismatch", "action": "Do not subtract Amazon Ads sales7d from Seller Central daily revenue. Add a true same-day paid revenue source or report over matching attribution windows."})
        return signals

    @staticmethod
    def _next_actions():
        return [
            "Keep using CampaignDailyDetail sales for ad performance, ACOS, and ROAS.",
            "Do not use CampaignDailyDetail sales7d as same-day paid revenue.",
            "Next build should add an ads metric audit endpoint and/or a true same-day revenue attribution strategy.",
        ]

    @staticmethod
    def _ads_attribution_warning():
        return {
            "level": "INFO",
            "message": "Amazon Ads campaign sales are currently sourced from sales7d and purchases7d. These are attribution-window metrics and can exceed same-day Seller Central revenue.",
            "impact": "Organic revenue and paid revenue ratios are intentionally returned as null rather than misleading zero/over-100% values.",
        }

    @staticmethod
    def _add_seller(bucket, row):
        bucket["total_revenue"] += RevenueReconciliationService._safe_float(row.ordered_product_sales)
        bucket["orders"] += RevenueReconciliationService._safe_int(row.total_order_items)
        bucket["units_ordered"] += RevenueReconciliationService._safe_int(row.units_ordered)
        bucket["sessions"] += RevenueReconciliationService._safe_int(row.sessions)
        bucket["page_views"] += RevenueReconciliationService._safe_int(row.page_views)

    @staticmethod
    def _add_ad_attribution(bucket, row):
        bucket["attributed_sales_7d"] += RevenueReconciliationService._safe_float(row.sales)
        bucket["ad_spend"] += RevenueReconciliationService._safe_float(row.spend)
        bucket["attributed_orders_7d"] += RevenueReconciliationService._safe_int(row.orders)
        bucket["clicks"] += RevenueReconciliationService._safe_int(row.clicks)
        bucket["impressions"] += RevenueReconciliationService._safe_int(row.impressions)

    @staticmethod
    def _seller_pipeline_status(db):
        latest_job = db.query(SPAPIReportJob).order_by(SPAPIReportJob.created_at.desc()).first()
        return {
            "seller_central_sales_traffic_rows": db.query(SellerCentralSalesTraffic).count(),
            "open_sales_traffic_jobs": db.query(SPAPIReportJob).filter(SPAPIReportJob.report_type == "GET_SALES_AND_TRAFFIC_REPORT").filter(SPAPIReportJob.status.in_(["REQUESTED", "PROCESSING", "DONE"])).count(),
            "collected_sales_traffic_jobs": db.query(SPAPIReportJob).filter(SPAPIReportJob.status == "COLLECTED").count(),
            "latest_job_status": latest_job.status if latest_job else None,
            "latest_job_processing_status": latest_job.processing_status if latest_job else None,
            "latest_job_marketplace": latest_job.marketplace if latest_job else None,
        }

    @staticmethod
    def _empty_response(alignment, debug=False):
        resp = {
            "status": "AWAITING_COMMON_DATA_DATE",
            "version": RevenueReconciliationService.version,
            "headline": "Organic versus paid revenue cannot be reconciled yet because Seller Central and Amazon Ads do not share a common date.",
            "data_freshness": alignment,
            "kpis": {
                "total_revenue": 0,
                "paid_revenue": None,
                "organic_revenue": None,
                "ad_attributed_sales_7d": 0,
                "ad_spend": 0,
                "orders": 0,
                "units_ordered": 0,
                "sessions": 0,
                "organic_ratio": None,
                "paid_ratio": None,
                "tacos": None,
                "conversion_rate": None,
                "advertising_dependency": "UNKNOWN",
                "confidence": 0,
            },
            "marketplaces": [],
            "data_quality_warnings": [RevenueReconciliationService._ads_attribution_warning()],
        }
        if debug:
            resp["debug"] = {}
        return resp

    @staticmethod
    def _canonical_market_key(country_code, marketplace, currency):
        country = (country_code or "").strip().upper()
        market = (marketplace or "").strip().lower()
        curr = (currency or "").strip().upper()
        if market in {"us", "usa", "united states", "amazon.com", "atvpdkikx0der"} or country in {"US", "ATVPDKIKX0DER"}:
            return ("US", "amazon.com", curr or "USD")
        if market in {"ca", "canada", "amazon.ca", "a2euq1wtgctbg2"} or country in {"CA", "A2EUQ1WTGCTBG2"}:
            return ("CA", "amazon.ca", curr or "CAD")
        if market in {"mx", "mexico", "amazon.com.mx", "a1am78c64um0y8"} or country in {"MX", "A1AM78C64UM0Y8"}:
            return ("MX", "amazon.com.mx", curr or "MXN")
        return ("UNKNOWN", "unknown", curr)

    @staticmethod
    def _seller_debug_row(row):
        return {"id": getattr(row, "id", None), "date": RevenueReconciliationService._date_str(row.date), "country_code": row.country_code, "marketplace": row.marketplace, "currency": row.currency, "sales": RevenueReconciliationService._safe_float(row.ordered_product_sales), "orders": RevenueReconciliationService._safe_int(row.total_order_items)}

    @staticmethod
    def _campaign_debug_row(row):
        return {"id": getattr(row, "id", None), "date": RevenueReconciliationService._date_str(row.date), "country_code": row.country_code, "marketplace": row.marketplace, "currency": row.currency, "campaign_name": row.campaign_name, "sales_field_sales7d": RevenueReconciliationService._safe_float(row.sales), "orders_field_purchases7d": RevenueReconciliationService._safe_int(row.orders), "spend": RevenueReconciliationService._safe_float(row.spend)}

    @staticmethod
    def _empty_seller_bucket():
        return {"total_revenue": 0.0, "orders": 0, "units_ordered": 0, "sessions": 0, "page_views": 0}

    @staticmethod
    def _empty_ad_bucket():
        return {"attributed_sales_7d": 0.0, "ad_spend": 0.0, "attributed_orders_7d": 0, "clicks": 0, "impressions": 0}

    @staticmethod
    def _ratio(numerator, denominator):
        return round(numerator / denominator, 4) if denominator else None

    @staticmethod
    def _date_only(value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return datetime.fromisoformat(str(value)).date()
        except Exception:
            return None

    @staticmethod
    def _date_str(value):
        value = RevenueReconciliationService._date_only(value)
        return value.isoformat() if value else None

    @staticmethod
    def _safe_float(value, default=0.0):
        try:
            return float(value if value is not None else default)
        except Exception:
            return default

    @staticmethod
    def _safe_int(value, default=0):
        try:
            return int(value if value is not None else default)
        except Exception:
            return default
