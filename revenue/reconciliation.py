"""Business OS v9.0.5 — Organic vs Paid reconciliation.

Fixes the real source issue seen in v9.0.4:
- Seller Central rows can include blank/unknown aggregate rows in addition to
  marketplace-specific rows.
- Ads rows can also include blank/unknown aggregate rows.
- Reconciliation must not sum aggregate rows with marketplace rows.

This service:
- Uses latest common date between Seller Central and Amazon Ads campaign-detail data.
- Uses SellerCentralSalesTraffic for total revenue/orders/sessions.
- Uses CampaignDailyDetail for paid-attributed ad revenue/spend.
- Normalizes marketplace identity before grouping.
- Drops unknown aggregate rows when country-specific rows exist.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

from database import SessionLocal
from models import CampaignDailyDetail, DailyDashboard, SPAPIReportJob, SellerCentralSalesTraffic


class RevenueReconciliationService:
    version = "9.0.5"

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

            seller_rows_raw = RevenueReconciliationService._seller_rows(db, aligned_date, country_code)
            seller_rows, seller_debug = RevenueReconciliationService._filter_seller_rows(seller_rows_raw)

            ad_rows_raw = RevenueReconciliationService._campaign_rows(db, aligned_date, country_code, profile_id)
            ad_rows, ad_debug = RevenueReconciliationService._filter_and_dedupe_campaign_rows(ad_rows_raw)

            seller_by_market = defaultdict(lambda: RevenueReconciliationService._empty_seller_bucket())
            for row in seller_rows:
                key = RevenueReconciliationService._canonical_market_key(row.country_code, row.marketplace, row.currency)
                RevenueReconciliationService._add_seller(seller_by_market[key], row)

            ads_by_market = defaultdict(lambda: RevenueReconciliationService._empty_ad_bucket())
            for row in ad_rows:
                key = RevenueReconciliationService._canonical_market_key(row.country_code, row.marketplace, row.currency)
                RevenueReconciliationService._add_ad(ads_by_market[key], row)

            keys = sorted(set(seller_by_market.keys()) | set(ads_by_market.keys()))
            marketplaces = []
            warnings = []

            for key in keys:
                country, marketplace, currency = key
                seller = seller_by_market.get(key, RevenueReconciliationService._empty_seller_bucket())
                ads = ads_by_market.get(key, RevenueReconciliationService._empty_ad_bucket())
                item = RevenueReconciliationService._marketplace_breakdown(country, marketplace, currency, seller, ads)
                if item["total_revenue"] > 0 and item["paid_revenue"] > item["total_revenue"]:
                    warnings.append({
                        "level": "WARNING",
                        "marketplace": item["label"],
                        "message": "Paid-attributed campaign revenue exceeds Seller Central total revenue for the aligned date. Check included campaign rows and attribution timing.",
                        "total_revenue": item["total_revenue"],
                        "paid_revenue": item["paid_revenue"],
                    })
                marketplaces.append(item)

            summary = RevenueReconciliationService._combine(marketplaces)
            status = "OK" if summary["total_revenue"] > 0 else "AWAITING_SELLER_CENTRAL_DATA"
            confidence = RevenueReconciliationService._confidence(summary, alignment, warnings)

            response = {
                "status": status,
                "version": RevenueReconciliationService.version,
                "headline": RevenueReconciliationService._headline(summary, alignment),
                "data_freshness": alignment,
                "seller_central_pipeline_status": RevenueReconciliationService._seller_pipeline_status(db),
                "kpis": {**summary, "confidence": confidence["score"], "confidence_reason": confidence},
                "marketplaces": marketplaces,
                "priority_signals": RevenueReconciliationService._priority_signals(summary, alignment, warnings),
                "next_actions": RevenueReconciliationService._next_actions(warnings),
                "data_quality_warnings": warnings,
                "reconciliation_source": {
                    "seller_central": "seller_central_sales_traffic exact aligned_date; blank aggregate rows ignored when marketplace rows exist",
                    "amazon_ads": "campaign_daily_details exact aligned_date; blank aggregate rows ignored and campaign rows de-duplicated",
                    "root_fix": "v9.0.5 prevents aggregate Seller Central / Ads rows from being summed with marketplace-specific rows.",
                },
            }

            if debug:
                response["debug"] = {
                    "seller_rows": seller_debug,
                    "ad_rows": ad_debug,
                    "marketplace_keys": {
                        "seller_keys": [list(k) for k in sorted(seller_by_market.keys())],
                        "ad_keys": [list(k) for k in sorted(ads_by_market.keys())],
                        "combined_keys": [list(k) for k in keys],
                    },
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
                "reconciliation_note": "v9.0.5 ignores blank aggregate Seller Central / Ads rows when marketplace-specific rows exist.",
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

        if not aligned_date:
            reason = "Seller Central and Amazon Ads campaign-detail data do not yet share a common date."
        elif aligned:
            reason = "Amazon Ads and Seller Central are aligned on the latest date."
        else:
            reason = "Amazon Ads and Seller Central data are not on the same latest date; using latest common date for reconciliation."

        return {
            "amazon_ads_latest_date": RevenueReconciliationService._date_str(ads_latest),
            "seller_central_latest_date": RevenueReconciliationService._date_str(seller_latest),
            "aligned_date": RevenueReconciliationService._date_str(aligned_date),
            "aligned": aligned,
            "reason": reason,
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
    def _filter_seller_rows(rows):
        marketplace_rows_exist = any(RevenueReconciliationService._is_marketplace_specific(row.country_code, row.marketplace) for row in rows)
        kept = []
        ignored = []

        for row in rows:
            if marketplace_rows_exist and not RevenueReconciliationService._is_marketplace_specific(row.country_code, row.marketplace):
                ignored.append(RevenueReconciliationService._seller_debug_row(row))
                continue
            kept.append(row)

        debug = {
            "raw_seller_rows": len(rows),
            "seller_rows_after_aggregate_filter": len(kept),
            "aggregate_seller_rows_ignored": len(ignored),
            "ignored_rows": ignored,
            "included_rows": [RevenueReconciliationService._seller_debug_row(row) for row in kept],
            "filter_rule": "If marketplace-specific Seller Central rows exist, blank/unknown aggregate Seller Central rows are ignored.",
        }
        return kept, debug

    @staticmethod
    def _filter_and_dedupe_campaign_rows(rows):
        marketplace_rows_exist = any(RevenueReconciliationService._is_marketplace_specific(row.country_code, row.marketplace) for row in rows)
        filtered = []
        ignored = []

        for row in rows:
            if marketplace_rows_exist and not RevenueReconciliationService._is_marketplace_specific(row.country_code, row.marketplace):
                ignored.append(RevenueReconciliationService._campaign_debug_row(row))
                continue
            filtered.append(row)

        selected = {}
        duplicates = 0
        for row in filtered:
            country, marketplace, currency = RevenueReconciliationService._canonical_market_key(row.country_code, row.marketplace, row.currency)
            campaign_key = str(row.campaign_id or row.campaign_name or getattr(row, "id", ""))
            key = (
                RevenueReconciliationService._date_str(row.date),
                row.profile_id or "",
                country,
                marketplace,
                currency,
                campaign_key,
            )
            existing = selected.get(key)
            if existing is None:
                selected[key] = row
            else:
                duplicates += 1
                if RevenueReconciliationService._row_sort_value(row) > RevenueReconciliationService._row_sort_value(existing):
                    selected[key] = row

        kept = list(selected.values())
        debug = {
            "raw_campaign_rows": len(rows),
            "campaign_rows_after_aggregate_filter": len(filtered),
            "aggregate_campaign_rows_ignored": len(ignored),
            "duplicate_campaign_rows_removed": duplicates,
            "deduped_campaign_rows": len(kept),
            "ignored_rows": ignored,
            "included_rows": [RevenueReconciliationService._campaign_debug_row(row) for row in kept],
            "filter_rule": "If marketplace-specific campaign rows exist, blank/unknown aggregate campaign rows are ignored; rows are then de-duplicated by campaign/date/profile/marketplace.",
        }
        return kept, debug

    @staticmethod
    def _is_marketplace_specific(country_code: str | None, marketplace: str | None) -> bool:
        country = (country_code or "").strip().upper()
        market = (marketplace or "").strip().lower()
        return country in {"US", "CA", "MX"} or market in {
            "us", "ca", "mx",
            "amazon.com", "amazon.ca", "amazon.com.mx",
            "atvpdkikx0der", "a2euq1wtgctbg2", "a1am78c64um0y8",
        }

    @staticmethod
    def _canonical_market_key(country_code: str | None, marketplace: str | None, currency: str | None) -> tuple[str, str, str]:
        country = (country_code or "").strip().upper()
        market = (marketplace or "").strip().lower()
        curr = (currency or "").strip().upper()

        if market in {"us", "usa", "united states", "amazon.com", "atvpdkikx0der"} or country == "US":
            return ("US", "amazon.com", curr or "USD")
        if market in {"ca", "canada", "amazon.ca", "a2euq1wtgctbg2"} or country == "CA":
            return ("CA", "amazon.ca", curr or "CAD")
        if market in {"mx", "mexico", "amazon.com.mx", "a1am78c64um0y8"} or country == "MX":
            return ("MX", "amazon.com.mx", curr or "MXN")
        return ("UNKNOWN", "unknown", curr)

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

    @staticmethod
    def _add_ad(bucket: dict[str, Any], row: CampaignDailyDetail) -> None:
        bucket["paid_revenue"] += RevenueReconciliationService._safe_float(row.sales)
        bucket["ad_spend"] += RevenueReconciliationService._safe_float(row.spend)
        bucket["orders"] += RevenueReconciliationService._safe_int(row.orders)
        bucket["clicks"] += RevenueReconciliationService._safe_int(row.clicks)
        bucket["impressions"] += RevenueReconciliationService._safe_int(row.impressions)

    @staticmethod
    def _marketplace_breakdown(country, marketplace, currency, seller, ads):
        total = RevenueReconciliationService._safe_float(seller.get("total_revenue"))
        paid = RevenueReconciliationService._safe_float(ads.get("paid_revenue"))
        spend = RevenueReconciliationService._safe_float(ads.get("ad_spend"))
        organic = max(total - paid, 0.0) if total > 0 else 0.0
        orders = RevenueReconciliationService._safe_int(seller.get("orders"))
        units = RevenueReconciliationService._safe_int(seller.get("units_ordered"))
        sessions = RevenueReconciliationService._safe_int(seller.get("sessions"))
        page_views = RevenueReconciliationService._safe_int(seller.get("page_views"))
        buy_box_count = RevenueReconciliationService._safe_int(seller.get("buy_box_count"))
        buy_box = RevenueReconciliationService._safe_float(seller.get("buy_box_sum")) / buy_box_count if buy_box_count else None

        return {
            "country_code": country,
            "marketplace": marketplace,
            "currency": currency,
            "label": f"{country} / {marketplace}",
            "channel": "amazon",
            "total_revenue": round(total, 2),
            "paid_revenue": round(paid, 2),
            "organic_revenue": round(organic, 2),
            "ad_spend": round(spend, 2),
            "orders": orders,
            "units_ordered": units,
            "sessions": sessions,
            "page_views": page_views,
            "paid_orders": RevenueReconciliationService._safe_int(ads.get("orders")),
            "ad_clicks": RevenueReconciliationService._safe_int(ads.get("clicks")),
            "ad_impressions": RevenueReconciliationService._safe_int(ads.get("impressions")),
            "organic_ratio": RevenueReconciliationService._ratio(organic, total),
            "paid_ratio": RevenueReconciliationService._ratio(paid, total),
            "tacos": RevenueReconciliationService._ratio(spend, total),
            "conversion_rate": RevenueReconciliationService._ratio(orders, sessions),
            "advertising_dependency": RevenueReconciliationService._dependency_label(paid, total),
            "buy_box_percentage": round(buy_box, 4) if buy_box is not None else None,
            "basis": "aggregate_rows_removed_then_seller_central_minus_campaign_daily_details",
        }

    @staticmethod
    def _combine(items):
        total = sum(RevenueReconciliationService._safe_float(i.get("total_revenue")) for i in items)
        paid = sum(RevenueReconciliationService._safe_float(i.get("paid_revenue")) for i in items)
        organic = max(total - paid, 0.0) if total > 0 else 0.0
        spend = sum(RevenueReconciliationService._safe_float(i.get("ad_spend")) for i in items)
        orders = sum(RevenueReconciliationService._safe_int(i.get("orders")) for i in items)
        units = sum(RevenueReconciliationService._safe_int(i.get("units_ordered")) for i in items)
        sessions = sum(RevenueReconciliationService._safe_int(i.get("sessions")) for i in items)
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
        }

    @staticmethod
    def _empty_response(alignment, debug=False):
        response = {
            "status": "AWAITING_COMMON_DATA_DATE",
            "version": RevenueReconciliationService.version,
            "headline": "Organic versus paid revenue cannot be reconciled yet because Seller Central and Amazon Ads do not share a common date.",
            "data_freshness": alignment,
            "kpis": {
                "total_revenue": 0,
                "paid_revenue": 0,
                "organic_revenue": 0,
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
                "confidence_reason": {"score": 0, "level": "LOW", "reason": alignment.get("reason")},
            },
            "marketplaces": [],
            "priority_signals": [],
            "next_actions": ["Run Seller Central collection and recheck data health."],
            "data_quality_warnings": [],
        }
        if debug:
            response["debug"] = {}
        return response

    @staticmethod
    def _confidence(summary, alignment, warnings):
        total = RevenueReconciliationService._safe_float(summary.get("total_revenue"))
        paid = RevenueReconciliationService._safe_float(summary.get("paid_revenue"))
        if total <= 0:
            return {"score": 0, "level": "LOW", "reason": "No Seller Central revenue is available for the aligned date.", "data_freshness": alignment}
        if paid > total:
            return {"score": 35, "level": "LOW", "reason": "Paid campaign revenue exceeds Seller Central revenue after aggregate-row cleanup. Review debug included campaign rows.", "data_freshness": alignment, "warnings": warnings}
        if not alignment.get("aligned"):
            return {"score": 75, "level": "MEDIUM", "reason": "Using latest common date because source latest dates differ.", "data_freshness": alignment}
        return {"score": 90, "level": "HIGH", "reason": "Seller Central and Amazon Ads are aligned on the same latest date.", "data_freshness": alignment}

    @staticmethod
    def _headline(summary, alignment):
        total = RevenueReconciliationService._safe_float(summary.get("total_revenue"))
        paid = RevenueReconciliationService._safe_float(summary.get("paid_revenue"))
        organic = RevenueReconciliationService._safe_float(summary.get("organic_revenue"))
        if total <= 0:
            return "Organic versus paid revenue cannot be calculated yet."
        note = "" if alignment.get("aligned") else " Sources were not on the same latest date, so this uses the latest common date."
        return f"Total revenue for {alignment.get('aligned_date')} is {total:.2f}; organic revenue is {organic:.2f} ({summary.get('organic_ratio')}), paid-attributed revenue is {paid:.2f} ({summary.get('paid_ratio')}), and TACOS is {summary.get('tacos')}.{note}"

    @staticmethod
    def _priority_signals(summary, alignment, warnings):
        signals = []
        if not alignment.get("aligned"):
            signals.append({"priority": "MEDIUM", "signal": "Data sources not fully aligned", "action": f"Using latest common date {alignment.get('aligned_date')}."})
        if warnings:
            signals.append({"priority": "HIGH", "signal": "Revenue attribution anomaly", "action": "Inspect debug seller/ad included rows."})
        return signals or [{"priority": "LOW", "signal": "Revenue mix stable", "action": "Continue monitoring organic vs paid trend."}]

    @staticmethod
    def _next_actions(warnings):
        actions = ["Run GET /business-os/revenue/organic-vs-paid?debug=true"]
        if warnings:
            actions.append("Review debug.seller_rows.included_rows and debug.ad_rows.included_rows.")
        return actions

    @staticmethod
    def _seller_pipeline_status(db):
        try:
            latest_job = db.query(SPAPIReportJob).order_by(SPAPIReportJob.created_at.desc()).first()
            return {
                "seller_central_sales_traffic_rows": db.query(SellerCentralSalesTraffic).count(),
                "open_sales_traffic_jobs": db.query(SPAPIReportJob).filter(SPAPIReportJob.report_type == "GET_SALES_AND_TRAFFIC_REPORT").filter(SPAPIReportJob.status.in_(["REQUESTED", "PROCESSING", "DONE"])).count(),
                "collected_sales_traffic_jobs": db.query(SPAPIReportJob).filter(SPAPIReportJob.status == "COLLECTED").count(),
                "latest_job_status": latest_job.status if latest_job else None,
                "latest_job_processing_status": latest_job.processing_status if latest_job else None,
                "latest_job_marketplace": latest_job.marketplace if latest_job else None,
            }
        except Exception as exc:
            return {"status": "ERROR", "message": str(exc)}

    @staticmethod
    def _seller_debug_row(row):
        return {
            "id": getattr(row, "id", None),
            "date": RevenueReconciliationService._date_str(row.date),
            "country_code": row.country_code,
            "marketplace": row.marketplace,
            "currency": row.currency,
            "asin": row.asin,
            "sku": row.sku,
            "ordered_product_sales": RevenueReconciliationService._safe_float(row.ordered_product_sales),
            "total_order_items": RevenueReconciliationService._safe_int(row.total_order_items),
            "units_ordered": RevenueReconciliationService._safe_int(row.units_ordered),
            "sessions": RevenueReconciliationService._safe_int(row.sessions),
        }

    @staticmethod
    def _campaign_debug_row(row):
        return {
            "id": getattr(row, "id", None),
            "date": RevenueReconciliationService._date_str(row.date),
            "profile_id": row.profile_id,
            "country_code": row.country_code,
            "marketplace": row.marketplace,
            "currency": row.currency,
            "campaign_id": str(row.campaign_id or ""),
            "campaign_name": row.campaign_name,
            "sales": RevenueReconciliationService._safe_float(row.sales),
            "spend": RevenueReconciliationService._safe_float(row.spend),
            "orders": RevenueReconciliationService._safe_int(row.orders),
        }

    @staticmethod
    def _row_sort_value(row):
        created = getattr(row, "created_at", None)
        created_value = created.timestamp() if isinstance(created, datetime) else 0
        return (created_value, getattr(row, "id", 0) or 0)

    @staticmethod
    def _empty_seller_bucket():
        return {"total_revenue": 0.0, "orders": 0, "units_ordered": 0, "sessions": 0, "page_views": 0, "buy_box_sum": 0.0, "buy_box_count": 0}

    @staticmethod
    def _empty_ad_bucket():
        return {"paid_revenue": 0.0, "ad_spend": 0.0, "orders": 0, "clicks": 0, "impressions": 0}

    @staticmethod
    def _dependency_label(paid, total):
        ratio = paid / total if total else 0
        if ratio >= 0.50:
            return "HIGH"
        if ratio >= 0.25:
            return "MEDIUM"
        if total > 0:
            return "LOW"
        return "UNKNOWN"

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
