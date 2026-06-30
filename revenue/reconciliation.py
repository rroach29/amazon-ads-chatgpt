"""Business OS v9.0.2 — Business Intelligence reconciliation service.

This service reconciles Amazon Ads revenue with Seller Central Sales & Traffic
data using the latest common date available across both sources. It prevents
Revenue Intelligence from returning zeros simply because Ads data is newer than
Seller Central data.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

from sqlalchemy import func

from database import SessionLocal
from models import DailyDashboard, SPAPIReportJob, SellerCentralSalesTraffic


class RevenueReconciliationService:
    version = "9.0.2"

    @staticmethod
    def organic_vs_paid(
        window: str = "latest",
        country_code: str | None = None,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        """Return organic-vs-paid revenue using the latest common date.

        Amazon Ads reports can arrive before Seller Central Sales & Traffic.
        When that happens, the service aligns to the newest date that exists in
        both datasets instead of returning zero Seller Central revenue.
        """

        db = SessionLocal()
        try:
            freshness = RevenueReconciliationService._data_freshness(
                db=db,
                country_code=country_code,
                profile_id=profile_id,
            )
            aligned_date = freshness.get("aligned_date")

            if not aligned_date:
                return RevenueReconciliationService._awaiting_data_response(
                    freshness=freshness,
                    country_code=country_code,
                    profile_id=profile_id,
                )

            seller_rows = RevenueReconciliationService._seller_rows_for_date(
                db=db,
                aligned_date=aligned_date,
                country_code=country_code,
            )
            ad_rows = RevenueReconciliationService._ad_rows_for_date(
                db=db,
                aligned_date=aligned_date,
                country_code=country_code,
                profile_id=profile_id,
            )

            marketplaces = RevenueReconciliationService._marketplace_items(
                seller_rows=seller_rows,
                ad_rows=ad_rows,
            )
            products = RevenueReconciliationService._product_items(seller_rows=seller_rows)
            summary = RevenueReconciliationService._combine(marketplaces)

            seller_status = "OK" if seller_rows else "AWAITING_SELLER_CENTRAL_DATA"
            status = "OK" if seller_status == "OK" else "AWAITING_SELLER_CENTRAL_DATA"

            return {
                "status": status,
                "version": RevenueReconciliationService.version,
                "data_context": {
                    "window_requested": window,
                    "reconciliation_window": "latest_common_date",
                    "start_date": str(aligned_date),
                    "end_date": str(aligned_date),
                    "country_code": country_code,
                    "profile_id": profile_id,
                    "source_of_truth": "latest common date across DailyDashboard and SellerCentralSalesTraffic",
                },
                "data_freshness": freshness,
                "seller_central_data_status": seller_status,
                "seller_central_pipeline_status": RevenueReconciliationService._seller_pipeline_status(),
                "summary": {
                    **summary,
                    "confidence_reason": RevenueReconciliationService._confidence_reason(
                        seller_status=seller_status,
                        freshness=freshness,
                    ),
                },
                "marketplaces": marketplaces,
                "products": products,
                "top_organic_strength": [
                    item for item in products
                    if item.get("organic_momentum") in {"STRONG", "BALANCED"}
                ][:10],
                "most_ad_dependent": sorted(
                    products,
                    key=lambda item: item.get("paid_ratio") or 0,
                    reverse=True,
                )[:10],
                "executive_narrative": RevenueReconciliationService._narrative(
                    summary=summary,
                    seller_status=seller_status,
                    freshness=freshness,
                ),
            }
        finally:
            db.close()

    @staticmethod
    def executive_snapshot(
        window: str = "latest",
        country_code: str | None = None,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        data = RevenueReconciliationService.organic_vs_paid(
            window=window,
            country_code=country_code,
            profile_id=profile_id,
        )
        return {
            "status": data.get("status"),
            "version": RevenueReconciliationService.version,
            "headline": data.get("executive_narrative"),
            "data_freshness": data.get("data_freshness"),
            "kpis": data.get("summary", {}),
            "priority_signals": RevenueReconciliationService._priority_signals(data),
            "next_actions": RevenueReconciliationService._next_actions(data),
        }

    @staticmethod
    def data_health(country_code: str | None = None, profile_id: str | None = None) -> dict[str, Any]:
        db = SessionLocal()
        try:
            freshness = RevenueReconciliationService._data_freshness(
                db=db,
                country_code=country_code,
                profile_id=profile_id,
            )
            pipeline = RevenueReconciliationService._seller_pipeline_status()
            return {
                "status": "OK" if freshness.get("aligned") else "PARTIAL",
                "version": RevenueReconciliationService.version,
                "data_freshness": freshness,
                "seller_central_pipeline_status": pipeline,
                "recommendation": RevenueReconciliationService._data_health_recommendation(freshness, pipeline),
            }
        finally:
            db.close()

    @staticmethod
    def _data_freshness(db, country_code: str | None = None, profile_id: str | None = None) -> dict[str, Any]:
        ad_query = db.query(func.max(DailyDashboard.date)).filter(DailyDashboard.channel == "amazon_ads")
        seller_query = db.query(func.max(SellerCentralSalesTraffic.date))

        if country_code:
            cc = country_code.upper()
            ad_query = ad_query.filter(func.upper(DailyDashboard.country_code) == cc)
            seller_query = seller_query.filter(func.upper(SellerCentralSalesTraffic.country_code) == cc)

        if profile_id:
            ad_query = ad_query.filter(DailyDashboard.profile_id == profile_id)
            seller_query = seller_query.filter(SellerCentralSalesTraffic.profile_id == profile_id)

        latest_ads_date = ad_query.scalar()
        latest_seller_date = seller_query.scalar()

        aligned_date = None
        if latest_ads_date and latest_seller_date:
            aligned_date = min(latest_ads_date, latest_seller_date)

        aligned = bool(
            latest_ads_date
            and latest_seller_date
            and latest_ads_date == latest_seller_date
        )

        if not latest_ads_date and not latest_seller_date:
            reason = "No Amazon Ads or Seller Central data is available."
        elif not latest_seller_date:
            reason = "Amazon Ads data is available, but Seller Central Sales & Traffic data has not been ingested."
        elif not latest_ads_date:
            reason = "Seller Central data is available, but Amazon Ads dashboard data is unavailable."
        elif latest_ads_date != latest_seller_date:
            reason = "Amazon Ads and Seller Central data are not on the same latest date; using latest common date for reconciliation."
        else:
            reason = "Amazon Ads and Seller Central data are aligned."

        return {
            "amazon_ads_latest_date": str(latest_ads_date) if latest_ads_date else None,
            "seller_central_latest_date": str(latest_seller_date) if latest_seller_date else None,
            "aligned_date": str(aligned_date) if aligned_date else None,
            "aligned": aligned,
            "reason": reason,
        }

    @staticmethod
    def _seller_rows_for_date(db, aligned_date: date | str, country_code: str | None = None):
        query = db.query(SellerCentralSalesTraffic).filter(SellerCentralSalesTraffic.date == aligned_date)
        if country_code:
            query = query.filter(func.upper(SellerCentralSalesTraffic.country_code) == country_code.upper())
        return query.all()

    @staticmethod
    def _ad_rows_for_date(db, aligned_date: date | str, country_code: str | None = None, profile_id: str | None = None):
        query = db.query(DailyDashboard).filter(DailyDashboard.channel == "amazon_ads").filter(DailyDashboard.date == aligned_date)
        if country_code:
            query = query.filter(func.upper(DailyDashboard.country_code) == country_code.upper())
        if profile_id:
            query = query.filter(DailyDashboard.profile_id == profile_id)
        return query.all()

    @staticmethod
    def _marketplace_items(seller_rows: list[Any], ad_rows: list[Any]) -> list[dict[str, Any]]:
        seller_by_key = defaultdict(lambda: RevenueReconciliationService._empty_seller_bucket())
        for row in seller_rows:
            key = RevenueReconciliationService._market_key(row.country_code, row.marketplace, row.currency)
            bucket = seller_by_key[key]
            RevenueReconciliationService._add_seller(bucket, row)

        ads_by_key = defaultdict(lambda: RevenueReconciliationService._empty_ad_bucket())
        for row in ad_rows:
            key = RevenueReconciliationService._market_key(row.country_code, row.marketplace, row.currency)
            bucket = ads_by_key[key]
            RevenueReconciliationService._add_ad(bucket, row)

        keys = sorted(set(seller_by_key.keys()) | set(ads_by_key.keys()))
        items = []
        for country, marketplace, currency in keys:
            seller = seller_by_key.get((country, marketplace, currency), RevenueReconciliationService._empty_seller_bucket())
            ads = ads_by_key.get((country, marketplace, currency), RevenueReconciliationService._empty_ad_bucket())
            item = RevenueReconciliationService._breakdown(
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
        return items

    @staticmethod
    def _product_items(seller_rows: list[Any]) -> list[dict[str, Any]]:
        seller_by_product = defaultdict(lambda: RevenueReconciliationService._empty_seller_bucket())
        for row in seller_rows:
            key = (
                row.asin or "unknown",
                row.sku or "",
                row.country_code or "",
                row.marketplace or "",
                row.currency or "",
            )
            bucket = seller_by_product[key]
            RevenueReconciliationService._add_seller(bucket, row)

        items = []
        for (asin, sku, country, marketplace, currency), seller in seller_by_product.items():
            item = RevenueReconciliationService._breakdown(
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
                ads=RevenueReconciliationService._empty_ad_bucket(),
                product_level=True,
            )
            items.append(item)

        items.sort(key=lambda item: (item.get("organic_revenue") or 0, item.get("total_revenue") or 0), reverse=True)
        return items

    @staticmethod
    def _seller_pipeline_status() -> dict[str, Any]:
        db = SessionLocal()
        try:
            seller_rows = db.query(SellerCentralSalesTraffic).count()
            open_jobs = (
                db.query(SPAPIReportJob)
                .filter(SPAPIReportJob.report_type == "GET_SALES_AND_TRAFFIC_REPORT")
                .filter(SPAPIReportJob.status.in_(["REQUESTED", "PROCESSING", "DONE"]))
                .count()
            )
            collected_jobs = (
                db.query(SPAPIReportJob)
                .filter(SPAPIReportJob.report_type == "GET_SALES_AND_TRAFFIC_REPORT")
                .filter(SPAPIReportJob.status == "COLLECTED")
                .count()
            )
            latest_job = db.query(SPAPIReportJob).order_by(SPAPIReportJob.created_at.desc()).first()
            return {
                "seller_central_sales_traffic_rows": seller_rows,
                "open_sales_traffic_jobs": open_jobs,
                "collected_sales_traffic_jobs": collected_jobs,
                "latest_job_status": latest_job.status if latest_job else None,
                "latest_job_processing_status": latest_job.processing_status if latest_job else None,
                "latest_job_marketplace": latest_job.marketplace if latest_job else None,
            }
        except Exception as exc:
            return {"status": "ERROR", "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def _empty_seller_bucket() -> dict[str, Any]:
        return {
            "total_revenue": 0.0,
            "orders": 0,
            "units_ordered": 0,
            "sessions": 0,
            "page_views": 0,
            "buy_box_sum": 0.0,
            "buy_box_count": 0,
            "title": None,
        }

    @staticmethod
    def _empty_ad_bucket() -> dict[str, Any]:
        return {
            "paid_revenue": 0.0,
            "ad_spend": 0.0,
            "orders": 0,
            "clicks": 0,
            "impressions": 0,
        }

    @staticmethod
    def _add_seller(bucket: dict[str, Any], row: SellerCentralSalesTraffic) -> None:
        bucket["total_revenue"] += RevenueReconciliationService._safe_float(row.ordered_product_sales)
        bucket["orders"] += RevenueReconciliationService._safe_int(row.total_order_items)
        bucket["units_ordered"] += RevenueReconciliationService._safe_int(row.units_ordered)
        bucket["sessions"] += RevenueReconciliationService._safe_int(row.sessions)
        bucket["page_views"] += RevenueReconciliationService._safe_int(row.page_views)
        if row.buy_box_percentage is not None:
            bucket["buy_box_sum"] += RevenueReconciliationService._safe_float(row.buy_box_percentage)
            bucket["buy_box_count"] += 1
        if row.title and not bucket.get("title"):
            bucket["title"] = row.title

    @staticmethod
    def _add_ad(bucket: dict[str, Any], row: DailyDashboard) -> None:
        bucket["paid_revenue"] += RevenueReconciliationService._safe_float(row.sales)
        bucket["ad_spend"] += RevenueReconciliationService._safe_float(row.spend)
        bucket["orders"] += RevenueReconciliationService._safe_int(row.orders)
        bucket["clicks"] += RevenueReconciliationService._safe_int(row.clicks)
        bucket["impressions"] += RevenueReconciliationService._safe_int(row.impressions)

    @staticmethod
    def _breakdown(identity: dict[str, Any], seller: dict[str, Any], ads: dict[str, Any], product_level: bool = False) -> dict[str, Any]:
        total = RevenueReconciliationService._safe_float(seller.get("total_revenue"))
        paid = RevenueReconciliationService._safe_float(ads.get("paid_revenue"))
        spend = RevenueReconciliationService._safe_float(ads.get("ad_spend"))
        organic = max(total - paid, 0.0) if total > 0 else 0.0
        confidence = 90 if total > 0 and not product_level else 70 if total > 0 else 15 if paid or spend else 0
        basis = "latest_common_date_seller_central_minus_paid_ads" if not product_level else "latest_common_date_seller_central_product_total"

        buy_box_count = RevenueReconciliationService._safe_int(seller.get("buy_box_count"))
        buy_box = (RevenueReconciliationService._safe_float(seller.get("buy_box_sum")) / buy_box_count) if buy_box_count else None
        sessions = RevenueReconciliationService._safe_int(seller.get("sessions"))
        orders = RevenueReconciliationService._safe_int(seller.get("orders") or ads.get("orders"))
        units = RevenueReconciliationService._safe_int(seller.get("units_ordered"))

        result = {
            **identity,
            "total_revenue": round(total, 2),
            "paid_revenue": round(paid, 2),
            "organic_revenue": round(organic, 2),
            "ad_spend": round(spend, 2),
            "orders": orders,
            "units_ordered": units,
            "sessions": sessions,
            "confidence": confidence,
            "basis": basis,
            "paid_ratio": RevenueReconciliationService._ratio(paid, total),
            "organic_ratio": RevenueReconciliationService._ratio(organic, total),
            "tacos": RevenueReconciliationService._ratio(spend, total),
            "conversion_rate": RevenueReconciliationService._ratio(orders, sessions),
            "advertising_dependency": RevenueReconciliationService._dependency_label(paid, total),
            "organic_momentum": RevenueReconciliationService._organic_momentum(organic, paid, total),
            "page_views": RevenueReconciliationService._safe_int(seller.get("page_views")),
            "buy_box_percentage": round(buy_box, 4) if buy_box is not None else None,
            "paid_orders": RevenueReconciliationService._safe_int(ads.get("orders")),
            "ad_clicks": RevenueReconciliationService._safe_int(ads.get("clicks")),
            "ad_impressions": RevenueReconciliationService._safe_int(ads.get("impressions")),
        }
        result["revenue_recommendation"] = RevenueReconciliationService._revenue_recommendation(result)
        return result

    @staticmethod
    def _combine(items: list[dict[str, Any]]) -> dict[str, Any]:
        total = sum(RevenueReconciliationService._safe_float(item.get("total_revenue")) for item in items)
        paid = sum(RevenueReconciliationService._safe_float(item.get("paid_revenue")) for item in items)
        organic = sum(RevenueReconciliationService._safe_float(item.get("organic_revenue")) for item in items)
        spend = sum(RevenueReconciliationService._safe_float(item.get("ad_spend")) for item in items)
        orders = sum(RevenueReconciliationService._safe_int(item.get("orders")) for item in items)
        units = sum(RevenueReconciliationService._safe_int(item.get("units_ordered")) for item in items)
        sessions = sum(RevenueReconciliationService._safe_int(item.get("sessions")) for item in items)
        confidence_values = [
            RevenueReconciliationService._safe_int(item.get("confidence"))
            for item in items
            if item.get("confidence") is not None
        ]
        confidence = round(sum(confidence_values) / len(confidence_values)) if confidence_values else 0

        return {
            "total_revenue": round(total, 2),
            "paid_revenue": round(paid, 2),
            "organic_revenue": round(organic, 2),
            "ad_spend": round(spend, 2),
            "orders": orders,
            "units_ordered": units,
            "sessions": sessions,
            "organic_ratio": RevenueReconciliationService._ratio(organic, total),
            "paid_ratio": RevenueReconciliationService._ratio(paid, total),
            "tacos": RevenueReconciliationService._ratio(spend, total),
            "conversion_rate": RevenueReconciliationService._ratio(orders, sessions),
            "advertising_dependency": RevenueReconciliationService._dependency_label(paid, total),
            "confidence": confidence,
        }

    @staticmethod
    def _confidence_reason(seller_status: str | None, freshness: dict[str, Any]) -> dict[str, Any]:
        pipeline = RevenueReconciliationService._seller_pipeline_status()
        if seller_status != "AWAITING_SELLER_CENTRAL_DATA":
            level = "HIGH" if freshness.get("aligned") else "MEDIUM"
            reason = (
                "Amazon Ads and Seller Central data are aligned."
                if freshness.get("aligned")
                else "Seller Central data exists and reconciliation used the latest common date because source dates differ."
            )
            return {
                "level": level,
                "reason": reason,
                "data_freshness": freshness,
                "pipeline": pipeline,
            }

        return {
            "level": "LOW",
            "reason": freshness.get("reason") or "Seller Central Sales & Traffic data is unavailable for reconciliation.",
            "data_freshness": freshness,
            "pipeline": pipeline,
            "recommended_action": "Collect open SP-API jobs or request a Sales & Traffic report for the selected window.",
        }

    @staticmethod
    def _priority_signals(data: dict[str, Any]) -> list[dict[str, Any]]:
        summary = data.get("summary", {})
        signals = []

        freshness = data.get("data_freshness", {})
        if freshness and not freshness.get("aligned") and freshness.get("aligned_date"):
            signals.append({
                "priority": "MEDIUM",
                "signal": "Data sources not fully aligned",
                "action": f"Using latest common date {freshness.get('aligned_date')} for reconciliation.",
            })

        if data.get("status") == "AWAITING_SELLER_CENTRAL_DATA":
            signals.append({
                "priority": "HIGH",
                "signal": "Seller Central data required",
                "action": "Run SP-API Sales & Traffic pipeline.",
            })
            return signals

        dep = summary.get("advertising_dependency")
        if dep == "HIGH":
            signals.append({
                "priority": "HIGH",
                "signal": "High advertising dependency",
                "action": "Review listing conversion and organic ranking before increasing ad spend.",
            })
        elif dep == "LOW":
            signals.append({
                "priority": "MEDIUM",
                "signal": "Strong organic contribution",
                "action": "Consider scaling profitable campaigns that support organic growth.",
            })

        tacos = summary.get("tacos")
        if isinstance(tacos, (int, float)) and tacos > 0.18:
            signals.append({
                "priority": "MEDIUM",
                "signal": "High TACOS",
                "action": "Focus on profit leaks, wasted spend, and listing conversion.",
            })

        return signals or [{
            "priority": "LOW",
            "signal": "Revenue mix stable",
            "action": "Continue monitoring organic vs paid trend.",
        }]

    @staticmethod
    def _next_actions(data: dict[str, Any]) -> list[str]:
        if data.get("status") == "AWAITING_SELLER_CENTRAL_DATA":
            return [
                "Run POST /business-os/sp-api/automation/open-jobs/collect",
                "If no jobs are open, run POST /business-os/sp-api/automation/nightly/run",
                "Then recheck GET /business-os/revenue/organic-vs-paid",
            ]
        return [
            "Review organic ratio against paid ratio in Mission Control.",
            "Review most ad-dependent products before increasing budgets.",
            "Use Product 360 to inspect products with weak organic contribution.",
        ]

    @staticmethod
    def _narrative(summary: dict[str, Any], seller_status: str | None, freshness: dict[str, Any]) -> str:
        if seller_status == "AWAITING_SELLER_CENTRAL_DATA" or RevenueReconciliationService._safe_float(summary.get("total_revenue")) <= 0:
            return "Seller Central Sales & Traffic data is required before organic versus paid revenue can be calculated."

        date_note = f" for {freshness.get('aligned_date')}" if freshness.get("aligned_date") else ""
        total = RevenueReconciliationService._safe_float(summary.get("total_revenue"))
        paid = RevenueReconciliationService._safe_float(summary.get("paid_revenue"))
        organic = RevenueReconciliationService._safe_float(summary.get("organic_revenue"))
        tacos = summary.get("tacos")
        organic_ratio = summary.get("organic_ratio")
        paid_ratio = summary.get("paid_ratio")
        alignment_note = "" if freshness.get("aligned") else " Sources were not on the same latest date, so this uses the latest common date."
        return (
            f"Total revenue{date_note} is {total:.2f}; organic revenue is {organic:.2f} "
            f"({organic_ratio}), paid-attributed revenue is {paid:.2f} ({paid_ratio}), "
            f"and TACOS is {tacos}.{alignment_note}"
        )

    @staticmethod
    def _data_health_recommendation(freshness: dict[str, Any], pipeline: dict[str, Any]) -> str:
        if freshness.get("aligned"):
            return "Amazon Ads and Seller Central data are aligned."
        if freshness.get("aligned_date"):
            return "Data sources are usable but not fully aligned; Revenue Intelligence will use the latest common date."
        if pipeline.get("open_sales_traffic_jobs"):
            return "Seller Central reports are still processing. Collect open jobs again later."
        return "Request or collect Seller Central Sales & Traffic reports."

    @staticmethod
    def _revenue_recommendation(item: dict[str, Any]) -> dict[str, Any]:
        total = RevenueReconciliationService._safe_float(item.get("total_revenue"))
        paid_ratio = item.get("paid_ratio")
        organic_ratio = item.get("organic_ratio")
        tacos = item.get("tacos")

        if total <= 0:
            return {
                "signal": "NO_TOTAL_REVENUE",
                "message": "Seller Central revenue is unavailable or zero for this row.",
            }
        if isinstance(paid_ratio, (int, float)) and paid_ratio >= 0.5:
            return {
                "signal": "HIGH_AD_DEPENDENCY",
                "message": "Paid-attributed revenue is a large share of total revenue. Review organic rank, listing quality, and TACOS before scaling spend.",
            }
        if isinstance(organic_ratio, (int, float)) and organic_ratio >= 0.65:
            return {
                "signal": "ORGANIC_STRENGTH",
                "message": "Organic revenue is carrying most sales. Consider scaling profitable ads that support organic growth.",
            }
        if isinstance(tacos, (int, float)) and tacos > 0.18:
            return {
                "signal": "HIGH_TACOS",
                "message": "Advertising spend is high relative to total revenue. Review wasted spend and listing conversion.",
            }
        return {
            "signal": "BALANCED_REVENUE_MIX",
            "message": "Organic and paid revenue mix appears balanced for this window.",
        }

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
    def _organic_momentum(organic: float, paid: float, total: float) -> str:
        if total <= 0:
            return "UNKNOWN"
        ratio = organic / total
        if ratio >= 0.65:
            return "STRONG"
        if ratio >= 0.45:
            return "BALANCED"
        if paid > organic:
            return "AD_DEPENDENT"
        return "WATCH"

    @staticmethod
    def _market_key(country_code: str | None, marketplace: str | None, currency: str | None) -> tuple[str, str, str]:
        return (str(country_code or "").upper(), str(marketplace or ""), str(currency or ""))

    @staticmethod
    def _ratio(numerator: float, denominator: float):
        return round(numerator / denominator, 4) if denominator else None

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
