"""Business OS v9.0.4 — Organic vs Paid reconciliation service.

Root fix:
- Normalize marketplace identity BEFORE grouping Seller Central and Ads rows.
- Seller Central may store marketplace as "US" / "CA" while Ads stores
  "amazon.com" / "amazon.ca". These are now reconciled to the same canonical key.
- Ignore blank/unknown aggregate Ads rows when country-specific Ads rows exist for
  the same aligned date to avoid double-counting.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

from database import SessionLocal
from models import DailyDashboard, SPAPIReportJob, SellerCentralSalesTraffic


class RevenueReconciliationService:
    version = "9.0.4"

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

            if not alignment.get("aligned_date"):
                return RevenueReconciliationService._empty_response(
                    alignment=alignment,
                    country_code=country_code,
                    profile_id=profile_id,
                    debug=debug,
                )

            aligned_date = alignment["aligned_date"]
            seller_rows = RevenueReconciliationService._seller_rows(
                db,
                aligned_date=aligned_date,
                country_code=country_code,
            )
            ad_rows, ad_debug = RevenueReconciliationService._deduped_daily_dashboard_rows(
                db,
                aligned_date=aligned_date,
                country_code=country_code,
                profile_id=profile_id,
            )

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
            warnings: list[dict[str, Any]] = []

            for key in keys:
                seller = seller_by_market.get(key, RevenueReconciliationService._empty_seller_bucket())
                ads = ads_by_market.get(key, RevenueReconciliationService._empty_ad_bucket())
                country, marketplace, currency = key
                item = RevenueReconciliationService._marketplace_breakdown(
                    country=country,
                    marketplace=marketplace,
                    currency=currency,
                    seller=seller,
                    ads=ads,
                )
                if item["paid_revenue"] > item["total_revenue"] and item["total_revenue"] > 0:
                    warnings.append(
                        {
                            "level": "WARNING",
                            "marketplace": item["label"],
                            "message": "Paid-attributed revenue exceeds Seller Central total revenue for the aligned date after canonical marketplace normalization.",
                            "total_revenue": item["total_revenue"],
                            "paid_revenue": item["paid_revenue"],
                            "source": "canonical_marketplace_reconciliation",
                        }
                    )
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
                "kpis": {
                    **summary,
                    "confidence": confidence["score"],
                    "confidence_reason": confidence,
                },
                "marketplaces": marketplaces,
                "priority_signals": RevenueReconciliationService._priority_signals(summary, alignment, warnings),
                "next_actions": RevenueReconciliationService._next_actions(status, warnings),
                "data_quality_warnings": warnings,
                "reconciliation_source": {
                    "seller_central": "seller_central_sales_traffic exact aligned_date, canonicalized marketplace key",
                    "amazon_ads": "daily_dashboards exact aligned_date, canonicalized marketplace key, latest row per date/profile/country/marketplace/currency",
                    "root_fix": "v9.0.4 normalizes marketplace identifiers before joining Seller Central and Ads.",
                },
            }
            if debug:
                response["debug"] = {
                    "seller_rows_included": len(seller_rows),
                    "ad_rows_included_after_dedupe": len(ad_rows),
                    "ad_dedupe": ad_debug,
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
            alignment = RevenueReconciliationService._alignment(db, country_code=country_code, profile_id=profile_id)
            seller_rows = db.query(SellerCentralSalesTraffic).count()
            dashboard_rows = db.query(DailyDashboard).filter(DailyDashboard.channel == "amazon_ads").count()
            pipeline = RevenueReconciliationService._seller_pipeline_status(db)
            return {
                "status": "OK",
                "version": RevenueReconciliationService.version,
                "data_freshness": alignment,
                "row_counts": {
                    "seller_central_sales_traffic": seller_rows,
                    "daily_dashboards_amazon_ads": dashboard_rows,
                },
                "seller_central_pipeline_status": pipeline,
                "reconciliation_note": "Revenue Intelligence uses the latest common date and canonical marketplace keys. US/amazon.com and CA/amazon.ca are normalized before reconciliation.",
            }
        finally:
            db.close()

    @staticmethod
    def _alignment(db, country_code: str | None = None, profile_id: str | None = None) -> dict[str, Any]:
        seller_query = db.query(SellerCentralSalesTraffic.date).filter(SellerCentralSalesTraffic.date.isnot(None))
        ads_query = db.query(DailyDashboard.date).filter(DailyDashboard.channel == "amazon_ads").filter(DailyDashboard.date.isnot(None))

        if country_code:
            cc = country_code.upper()
            seller_query = seller_query.filter(SellerCentralSalesTraffic.country_code == cc)
            ads_query = ads_query.filter(DailyDashboard.country_code == cc)
        if profile_id:
            ads_query = ads_query.filter(DailyDashboard.profile_id == profile_id)

        seller_dates = {RevenueReconciliationService._date_only(row[0]) for row in seller_query.distinct().all() if row[0]}
        ads_dates = {RevenueReconciliationService._date_only(row[0]) for row in ads_query.distinct().all() if row[0]}

        seller_dates.discard(None)
        ads_dates.discard(None)

        seller_latest = max(seller_dates) if seller_dates else None
        ads_latest = max(ads_dates) if ads_dates else None
        common_dates = seller_dates & ads_dates
        aligned_date = max(common_dates) if common_dates else None
        aligned = bool(aligned_date and seller_latest == ads_latest == aligned_date)

        if not seller_latest and not ads_latest:
            reason = "No Seller Central or Amazon Ads dates are available."
        elif not seller_latest:
            reason = "Amazon Ads data exists, but Seller Central Sales & Traffic data is not available yet."
        elif not ads_latest:
            reason = "Seller Central data exists, but Amazon Ads dashboard data is not available yet."
        elif not aligned_date:
            reason = "Seller Central and Amazon Ads have data, but no overlapping date was found."
        elif not aligned:
            reason = "Amazon Ads and Seller Central data are not on the same latest date; using latest common date for reconciliation."
        else:
            reason = "Amazon Ads and Seller Central are aligned on the latest date."

        return {
            "amazon_ads_latest_date": RevenueReconciliationService._date_str(ads_latest),
            "seller_central_latest_date": RevenueReconciliationService._date_str(seller_latest),
            "aligned_date": RevenueReconciliationService._date_str(aligned_date),
            "aligned": aligned,
            "reason": reason,
        }

    @staticmethod
    def _seller_rows(db, aligned_date: str, country_code: str | None = None):
        query = db.query(SellerCentralSalesTraffic).filter(SellerCentralSalesTraffic.date == aligned_date)
        if country_code:
            query = query.filter(SellerCentralSalesTraffic.country_code == country_code.upper())
        return query.all()

    @staticmethod
    def _deduped_daily_dashboard_rows(db, aligned_date: str, country_code: str | None = None, profile_id: str | None = None):
        query = (
            db.query(DailyDashboard)
            .filter(DailyDashboard.channel == "amazon_ads")
            .filter(DailyDashboard.date == aligned_date)
        )
        if country_code:
            query = query.filter(DailyDashboard.country_code == country_code.upper())
        if profile_id:
            query = query.filter(DailyDashboard.profile_id == profile_id)

        rows = query.all()

        # If country-specific ad rows exist, blank/unknown country rows are likely
        # aggregate rows and must not be summed with country rows.
        country_specific_exists = any((row.country_code or "").strip() for row in rows)
        filtered_rows = []
        ignored_unknown_rows = []
        for row in rows:
            if country_specific_exists and not (row.country_code or "").strip():
                ignored_unknown_rows.append(getattr(row, "id", None))
                continue
            filtered_rows.append(row)

        selected: dict[tuple[Any, ...], DailyDashboard] = {}
        duplicates = 0

        for row in filtered_rows:
            country, marketplace, currency = RevenueReconciliationService._canonical_market_key(row.country_code, row.marketplace, row.currency)
            key = (
                RevenueReconciliationService._date_str(row.date),
                row.profile_id or "",
                country,
                marketplace,
                currency,
            )
            existing = selected.get(key)
            if existing is None:
                selected[key] = row
                continue

            duplicates += 1
            existing_sort = RevenueReconciliationService._row_sort_value(existing)
            row_sort = RevenueReconciliationService._row_sort_value(row)
            if row_sort > existing_sort:
                selected[key] = row

        kept = list(selected.values())
        debug = {
            "raw_daily_dashboard_rows": len(rows),
            "unknown_aggregate_rows_ignored": len(ignored_unknown_rows),
            "ignored_unknown_row_ids": ignored_unknown_rows,
            "rows_after_unknown_filter": len(filtered_rows),
            "deduped_daily_dashboard_rows": len(kept),
            "duplicate_rows_removed": duplicates,
            "dedupe_key": ["date", "profile_id", "canonical_country_code", "canonical_marketplace", "currency"],
            "included_row_ids": [getattr(row, "id", None) for row in kept],
            "source": "daily_dashboards",
        }
        return kept, debug

    @staticmethod
    def _canonical_market_key(country_code: str | None, marketplace: str | None, currency: str | None) -> tuple[str, str, str]:
        country = (country_code or "").strip().upper()
        market = (marketplace or "").strip().lower()
        curr = (currency or "").strip().upper()

        # Marketplace occasionally arrives as a country code from Seller Central.
        if market in {"us", "usa", "united states", "amazon.com", "atvpdkikx0der"} or country == "US":
            return ("US", "amazon.com", curr or "USD")
        if market in {"ca", "canada", "amazon.ca", "a2euq1wtgctbg2"} or country == "CA":
            return ("CA", "amazon.ca", curr or "CAD")
        if market in {"mx", "mexico", "amazon.com.mx", "a1am78c64um0y8"} or country == "MX":
            return ("MX", "amazon.com.mx", curr or "MXN")

        return (country, market, curr)

    @staticmethod
    def _row_sort_value(row: DailyDashboard):
        created = getattr(row, "created_at", None)
        if isinstance(created, datetime):
            created_value = created.timestamp()
        else:
            created_value = 0
        row_id = getattr(row, "id", 0) or 0
        return (created_value, row_id)

    @staticmethod
    def _empty_response(alignment: dict[str, Any], country_code: str | None, profile_id: str | None, debug: bool) -> dict[str, Any]:
        response = {
            "status": "AWAITING_COMMON_DATA_DATE",
            "version": RevenueReconciliationService.version,
            "headline": "Organic versus paid revenue cannot be reconciled yet because Seller Central and Amazon Ads do not share a common date.",
            "data_freshness": alignment,
            "seller_central_pipeline_status": RevenueReconciliationService._seller_pipeline_status(),
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
                "confidence_reason": {
                    "level": "LOW",
                    "reason": alignment.get("reason"),
                    "data_freshness": alignment,
                },
            },
            "marketplaces": [],
            "priority_signals": [
                {
                    "priority": "HIGH",
                    "signal": "No common reconciliation date",
                    "action": "Collect Seller Central Sales & Traffic jobs and ensure Amazon Ads dashboard data exists for the same date.",
                }
            ],
            "next_actions": [
                "Run POST /business-os/sp-api/automation/open-jobs/collect",
                "Run GET /business-os/revenue/data-health",
            ],
            "data_quality_warnings": [],
        }
        if debug:
            response["debug"] = {"country_code": country_code, "profile_id": profile_id}
        return response

    @staticmethod
    def _marketplace_breakdown(country: str, marketplace: str, currency: str, seller: dict[str, Any], ads: dict[str, Any]) -> dict[str, Any]:
        total = RevenueReconciliationService._safe_float(seller.get("total_revenue"))
        paid = RevenueReconciliationService._safe_float(ads.get("paid_revenue"))
        spend = RevenueReconciliationService._safe_float(ads.get("ad_spend"))
        organic = max(total - paid, 0.0) if total > 0 else 0.0
        orders = RevenueReconciliationService._safe_int(seller.get("orders") or ads.get("orders"))
        units = RevenueReconciliationService._safe_int(seller.get("units_ordered"))
        sessions = RevenueReconciliationService._safe_int(seller.get("sessions"))
        page_views = RevenueReconciliationService._safe_int(seller.get("page_views"))
        buy_box_count = RevenueReconciliationService._safe_int(seller.get("buy_box_count"))
        buy_box = (RevenueReconciliationService._safe_float(seller.get("buy_box_sum")) / buy_box_count) if buy_box_count else None

        return {
            "country_code": country,
            "marketplace": marketplace,
            "currency": currency,
            "label": f"{country or 'Unknown'} / {marketplace or 'unknown'}",
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
            "basis": "canonical_seller_central_minus_canonical_deduped_daily_dashboard",
        }

    @staticmethod
    def _combine(items: list[dict[str, Any]]) -> dict[str, Any]:
        total = sum(RevenueReconciliationService._safe_float(item.get("total_revenue")) for item in items)
        paid = sum(RevenueReconciliationService._safe_float(item.get("paid_revenue")) for item in items)
        organic = max(total - paid, 0.0) if total > 0 else 0.0
        spend = sum(RevenueReconciliationService._safe_float(item.get("ad_spend")) for item in items)
        orders = sum(RevenueReconciliationService._safe_int(item.get("orders")) for item in items)
        units = sum(RevenueReconciliationService._safe_int(item.get("units_ordered")) for item in items)
        sessions = sum(RevenueReconciliationService._safe_int(item.get("sessions")) for item in items)
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
    def _seller_pipeline_status(db=None) -> dict[str, Any]:
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True
        try:
            seller_rows = db.query(SellerCentralSalesTraffic).count()
            open_jobs = (
                db.query(SPAPIReportJob)
                .filter(SPAPIReportJob.report_type == "GET_SALES_AND_TRAFFIC_REPORT")
                .filter(SPAPIReportJob.status.in_(["REQUESTED", "PROCESSING", "DONE"]))
                .count()
            )
            collected_jobs = db.query(SPAPIReportJob).filter(SPAPIReportJob.status == "COLLECTED").count()
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
            if close_db:
                db.close()

    @staticmethod
    def _confidence(summary: dict[str, Any], alignment: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
        total = RevenueReconciliationService._safe_float(summary.get("total_revenue"))
        paid = RevenueReconciliationService._safe_float(summary.get("paid_revenue"))
        if total <= 0:
            return {"score": 0, "level": "LOW", "reason": "No Seller Central total revenue is available for the aligned date.", "data_freshness": alignment}
        if paid > total:
            return {"score": 35, "level": "LOW", "reason": "Paid-attributed revenue exceeds Seller Central total revenue after canonical marketplace normalization.", "data_freshness": alignment, "warnings": warnings}
        if not alignment.get("aligned"):
            return {"score": 75, "level": "MEDIUM", "reason": "Reconciliation used the latest common date because source latest dates differ.", "data_freshness": alignment}
        return {"score": 90, "level": "HIGH", "reason": "Seller Central and Amazon Ads are aligned on the same latest date.", "data_freshness": alignment}

    @staticmethod
    def _priority_signals(summary: dict[str, Any], alignment: dict[str, Any], warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        signals = []
        if not alignment.get("aligned"):
            signals.append({"priority": "MEDIUM", "signal": "Data sources not fully aligned", "action": f"Using latest common date {alignment.get('aligned_date')} for reconciliation."})
        if warnings:
            signals.append({"priority": "HIGH", "signal": "Revenue attribution anomaly", "action": "Inspect debug marketplace keys and included dashboard rows."})
        dependency = summary.get("advertising_dependency")
        if dependency == "HIGH":
            signals.append({"priority": "HIGH", "signal": "High advertising dependency", "action": "Review listing conversion and organic ranking before increasing ad spend."})
        tacos = summary.get("tacos")
        if isinstance(tacos, (int, float)) and tacos > 0.18:
            signals.append({"priority": "MEDIUM", "signal": "High TACOS", "action": "Focus on profit leaks, wasted spend, and listing conversion."})
        return signals or [{"priority": "LOW", "signal": "Revenue mix stable", "action": "Continue monitoring organic vs paid trend."}]

    @staticmethod
    def _next_actions(status: str, warnings: list[dict[str, Any]]) -> list[str]:
        actions = ["Run GET /business-os/revenue/data-health", "Run GET /business-os/revenue/organic-vs-paid?debug=true"]
        if status != "OK":
            actions.append("Collect open Seller Central jobs or request a Sales & Traffic report for the aligned date.")
        if warnings:
            actions.append("Review debug.marketplace_keys and debug.ad_dedupe to confirm Seller Central and Ads are matched by canonical marketplace.")
        return actions

    @staticmethod
    def _headline(summary: dict[str, Any], alignment: dict[str, Any]) -> str:
        total = RevenueReconciliationService._safe_float(summary.get("total_revenue"))
        paid = RevenueReconciliationService._safe_float(summary.get("paid_revenue"))
        organic = RevenueReconciliationService._safe_float(summary.get("organic_revenue"))
        tacos = summary.get("tacos")
        aligned_date = alignment.get("aligned_date")
        if total <= 0:
            return f"Organic versus paid revenue cannot be calculated yet for {aligned_date or 'the selected window'}."
        note = "" if alignment.get("aligned") else " Sources were not on the same latest date, so this uses the latest common date."
        return f"Total revenue for {aligned_date} is {total:.2f}; organic revenue is {organic:.2f} ({summary.get('organic_ratio')}), paid-attributed revenue is {paid:.2f} ({summary.get('paid_ratio')}), and TACOS is {tacos}.{note}"

    @staticmethod
    def _empty_seller_bucket() -> dict[str, Any]:
        return {"total_revenue": 0.0, "orders": 0, "units_ordered": 0, "sessions": 0, "page_views": 0, "buy_box_sum": 0.0, "buy_box_count": 0}

    @staticmethod
    def _empty_ad_bucket() -> dict[str, Any]:
        return {"paid_revenue": 0.0, "ad_spend": 0.0, "orders": 0, "clicks": 0, "impressions": 0}

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
    def _add_ad(bucket: dict[str, Any], row: DailyDashboard) -> None:
        bucket["paid_revenue"] += RevenueReconciliationService._safe_float(row.sales)
        bucket["ad_spend"] += RevenueReconciliationService._safe_float(row.spend)
        bucket["orders"] += RevenueReconciliationService._safe_int(row.orders)
        bucket["clicks"] += RevenueReconciliationService._safe_int(row.clicks)
        bucket["impressions"] += RevenueReconciliationService._safe_int(row.impressions)

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
    def _date_only(value: Any):
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
    def _date_str(value: Any):
        value = RevenueReconciliationService._date_only(value)
        return value.isoformat() if value else None

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
