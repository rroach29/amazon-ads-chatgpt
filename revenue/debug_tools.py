"""Business OS v9.0.6 — Seller Central debug and cleanup tools.

These helpers expose safe Swagger-accessible actions so duplicate SP-API imports
can be inspected and cleaned without running SQL manually.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

from database import SessionLocal
from models import SellerCentralSalesTraffic


class SellerCentralDebugService:
    version = "9.0.6"

    @staticmethod
    def rows(date_value: str, country_code: str | None = None, limit: int = 500) -> dict[str, Any]:
        target_date = SellerCentralDebugService._parse_date(date_value)
        db = SessionLocal()
        try:
            query = db.query(SellerCentralSalesTraffic).filter(SellerCentralSalesTraffic.date == target_date)
            if country_code:
                query = query.filter(SellerCentralSalesTraffic.country_code == country_code.upper())

            rows = query.order_by(
                SellerCentralSalesTraffic.country_code.asc(),
                SellerCentralSalesTraffic.marketplace.asc(),
                SellerCentralSalesTraffic.asin.asc(),
                SellerCentralSalesTraffic.sku.asc(),
                SellerCentralSalesTraffic.id.asc(),
            ).limit(max(1, min(limit, 2000))).all()

            totals = SellerCentralDebugService._totals(rows)
            return {
                "status": "OK",
                "version": SellerCentralDebugService.version,
                "date": target_date.isoformat(),
                "country_code": country_code.upper() if country_code else None,
                "row_count": len(rows),
                "totals": totals,
                "rows": [SellerCentralDebugService._row_to_dict(row) for row in rows],
                "note": "This endpoint shows raw seller_central_sales_traffic rows. If row_count/totals are too high, run the duplicate diagnostic and cleanup dry-run next.",
            }
        finally:
            db.close()

    @staticmethod
    def duplicates(date_value: str, country_code: str | None = None) -> dict[str, Any]:
        target_date = SellerCentralDebugService._parse_date(date_value)
        db = SessionLocal()
        try:
            query = db.query(SellerCentralSalesTraffic).filter(SellerCentralSalesTraffic.date == target_date)
            if country_code:
                query = query.filter(SellerCentralSalesTraffic.country_code == country_code.upper())
            rows = query.order_by(SellerCentralSalesTraffic.id.asc()).all()

            groups = SellerCentralDebugService._group_rows(rows)
            duplicate_groups = []
            duplicate_row_ids = []

            for key, items in groups.items():
                if len(items) <= 1:
                    continue
                keep = SellerCentralDebugService._choose_keep_row(items)
                delete_candidates = [row for row in items if row.id != keep.id]
                duplicate_row_ids.extend([row.id for row in delete_candidates])
                duplicate_groups.append({
                    "logical_key": SellerCentralDebugService._key_to_dict(key),
                    "row_count": len(items),
                    "keep_row_id": keep.id,
                    "delete_candidate_ids": [row.id for row in delete_candidates],
                    "group_totals_before_cleanup": SellerCentralDebugService._totals(items),
                    "kept_row": SellerCentralDebugService._row_to_dict(keep),
                    "duplicate_rows": [SellerCentralDebugService._row_to_dict(row) for row in delete_candidates],
                })

            return {
                "status": "OK",
                "version": SellerCentralDebugService.version,
                "date": target_date.isoformat(),
                "country_code": country_code.upper() if country_code else None,
                "raw_row_count": len(rows),
                "logical_group_count": len(groups),
                "duplicate_group_count": len(duplicate_groups),
                "duplicate_row_count": len(duplicate_row_ids),
                "totals_before_cleanup": SellerCentralDebugService._totals(rows),
                "estimated_totals_after_cleanup": SellerCentralDebugService._totals([SellerCentralDebugService._choose_keep_row(items) for items in groups.values()]),
                "duplicate_groups": duplicate_groups[:250],
                "note": "Duplicate groups are based on date + marketplace identity + asin + sku + title + report_type. Cleanup keeps the newest/highest-id row in each group.",
            }
        finally:
            db.close()

    @staticmethod
    def cleanup_duplicates(date_value: str, country_code: str | None = None, dry_run: bool = True) -> dict[str, Any]:
        target_date = SellerCentralDebugService._parse_date(date_value)
        db = SessionLocal()
        try:
            query = db.query(SellerCentralSalesTraffic).filter(SellerCentralSalesTraffic.date == target_date)
            if country_code:
                query = query.filter(SellerCentralSalesTraffic.country_code == country_code.upper())
            rows = query.order_by(SellerCentralSalesTraffic.id.asc()).all()

            groups = SellerCentralDebugService._group_rows(rows)
            keep_rows = []
            delete_rows = []
            for items in groups.values():
                keep = SellerCentralDebugService._choose_keep_row(items)
                keep_rows.append(keep)
                delete_rows.extend([row for row in items if row.id != keep.id])

            delete_ids = [row.id for row in delete_rows]

            if not dry_run and delete_ids:
                for row in delete_rows:
                    db.delete(row)
                db.commit()

            return {
                "status": "DRY_RUN" if dry_run else "CLEANED",
                "version": SellerCentralDebugService.version,
                "date": target_date.isoformat(),
                "country_code": country_code.upper() if country_code else None,
                "raw_row_count_before": len(rows),
                "logical_row_count_after": len(keep_rows),
                "duplicate_rows_to_delete": len(delete_rows),
                "deleted_row_ids": [] if dry_run else delete_ids,
                "candidate_delete_row_ids": delete_ids if dry_run else [],
                "totals_before_cleanup": SellerCentralDebugService._totals(rows),
                "estimated_totals_after_cleanup": SellerCentralDebugService._totals(keep_rows),
                "dry_run": dry_run,
                "next_step": "If dry_run looks correct, run the same action with dry_run=false.",
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def aggregate_rows(date_value: str, country_code: str | None = None) -> dict[str, Any]:
        target_date = SellerCentralDebugService._parse_date(date_value)
        db = SessionLocal()
        try:
            query = db.query(SellerCentralSalesTraffic).filter(SellerCentralSalesTraffic.date == target_date)
            if country_code:
                query = query.filter(SellerCentralSalesTraffic.country_code == country_code.upper())
            rows = query.all()
            aggregate_rows = [row for row in rows if not SellerCentralDebugService._is_marketplace_specific(row)]
            marketplace_rows = [row for row in rows if SellerCentralDebugService._is_marketplace_specific(row)]
            return {
                "status": "OK",
                "version": SellerCentralDebugService.version,
                "date": target_date.isoformat(),
                "country_code": country_code.upper() if country_code else None,
                "total_rows": len(rows),
                "marketplace_specific_rows": len(marketplace_rows),
                "aggregate_or_unknown_rows": len(aggregate_rows),
                "marketplace_specific_totals": SellerCentralDebugService._totals(marketplace_rows),
                "aggregate_or_unknown_totals": SellerCentralDebugService._totals(aggregate_rows),
                "aggregate_or_unknown_row_ids": [row.id for row in aggregate_rows],
                "aggregate_or_unknown_rows_detail": [SellerCentralDebugService._row_to_dict(row) for row in aggregate_rows[:500]],
                "note": "Aggregate/unknown rows should generally not be added to marketplace-specific rows. Use this to confirm whether imported reports contain both levels.",
            }
        finally:
            db.close()

    @staticmethod
    def cleanup_aggregate_rows(date_value: str, country_code: str | None = None, dry_run: bool = True) -> dict[str, Any]:
        target_date = SellerCentralDebugService._parse_date(date_value)
        db = SessionLocal()
        try:
            query = db.query(SellerCentralSalesTraffic).filter(SellerCentralSalesTraffic.date == target_date)
            if country_code:
                query = query.filter(SellerCentralSalesTraffic.country_code == country_code.upper())
            rows = query.all()

            marketplace_rows = [row for row in rows if SellerCentralDebugService._is_marketplace_specific(row)]
            aggregate_rows = [row for row in rows if not SellerCentralDebugService._is_marketplace_specific(row)]

            # Only delete aggregate rows when marketplace-specific rows exist for the same date/scope.
            delete_rows = aggregate_rows if marketplace_rows else []
            delete_ids = [row.id for row in delete_rows]

            if not dry_run and delete_rows:
                for row in delete_rows:
                    db.delete(row)
                db.commit()

            return {
                "status": "DRY_RUN" if dry_run else "CLEANED",
                "version": SellerCentralDebugService.version,
                "date": target_date.isoformat(),
                "country_code": country_code.upper() if country_code else None,
                "marketplace_specific_rows": len(marketplace_rows),
                "aggregate_or_unknown_rows": len(aggregate_rows),
                "aggregate_rows_to_delete": len(delete_rows),
                "candidate_delete_row_ids": delete_ids if dry_run else [],
                "deleted_row_ids": [] if dry_run else delete_ids,
                "totals_before_cleanup": SellerCentralDebugService._totals(rows),
                "estimated_totals_after_cleanup": SellerCentralDebugService._totals([row for row in rows if row.id not in set(delete_ids)]),
                "dry_run": dry_run,
                "safety_rule": "Aggregate rows are only deleted if marketplace-specific rows exist for the same date/scope.",
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _group_rows(rows: list[SellerCentralSalesTraffic]) -> dict[tuple[Any, ...], list[SellerCentralSalesTraffic]]:
        groups: dict[tuple[Any, ...], list[SellerCentralSalesTraffic]] = defaultdict(list)
        for row in rows:
            groups[SellerCentralDebugService._logical_key(row)].append(row)
        return groups

    @staticmethod
    def _logical_key(row: SellerCentralSalesTraffic) -> tuple[Any, ...]:
        country, marketplace, currency = SellerCentralDebugService._canonical_market_key(row.country_code, row.marketplace, row.currency)
        return (
            SellerCentralDebugService._date_str(row.date),
            country,
            marketplace,
            currency,
            (row.asin or "").strip(),
            (row.sku or "").strip(),
            (row.title or "").strip(),
            (row.report_type or "GET_SALES_AND_TRAFFIC_REPORT").strip(),
        )

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
    def _is_marketplace_specific(row: SellerCentralSalesTraffic) -> bool:
        country, marketplace, _ = SellerCentralDebugService._canonical_market_key(row.country_code, row.marketplace, row.currency)
        return country in {"US", "CA", "MX"} and marketplace != "unknown"

    @staticmethod
    def _choose_keep_row(rows: list[SellerCentralSalesTraffic]) -> SellerCentralSalesTraffic:
        def sort_value(row: SellerCentralSalesTraffic):
            created = row.created_at.timestamp() if isinstance(row.created_at, datetime) else 0
            return (created, row.id or 0)
        return sorted(rows, key=sort_value, reverse=True)[0]

    @staticmethod
    def _totals(rows: list[SellerCentralSalesTraffic]) -> dict[str, Any]:
        return {
            "ordered_product_sales": round(sum(SellerCentralDebugService._safe_float(row.ordered_product_sales) for row in rows), 2),
            "total_order_items": sum(SellerCentralDebugService._safe_int(row.total_order_items) for row in rows),
            "units_ordered": sum(SellerCentralDebugService._safe_int(row.units_ordered) for row in rows),
            "sessions": sum(SellerCentralDebugService._safe_int(row.sessions) for row in rows),
            "page_views": sum(SellerCentralDebugService._safe_int(row.page_views) for row in rows),
        }

    @staticmethod
    def _row_to_dict(row: SellerCentralSalesTraffic) -> dict[str, Any]:
        country, marketplace, currency = SellerCentralDebugService._canonical_market_key(row.country_code, row.marketplace, row.currency)
        return {
            "id": row.id,
            "date": SellerCentralDebugService._date_str(row.date),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "country_code": row.country_code,
            "marketplace": row.marketplace,
            "currency": row.currency,
            "canonical_country_code": country,
            "canonical_marketplace": marketplace,
            "canonical_currency": currency,
            "asin": row.asin,
            "sku": row.sku,
            "title": row.title,
            "ordered_product_sales": SellerCentralDebugService._safe_float(row.ordered_product_sales),
            "units_ordered": SellerCentralDebugService._safe_int(row.units_ordered),
            "total_order_items": SellerCentralDebugService._safe_int(row.total_order_items),
            "sessions": SellerCentralDebugService._safe_int(row.sessions),
            "page_views": SellerCentralDebugService._safe_int(row.page_views),
            "buy_box_percentage": row.buy_box_percentage,
            "unit_session_percentage": row.unit_session_percentage,
            "report_type": row.report_type,
            "is_marketplace_specific": SellerCentralDebugService._is_marketplace_specific(row),
        }

    @staticmethod
    def _key_to_dict(key: tuple[Any, ...]) -> dict[str, Any]:
        return {
            "date": key[0],
            "country_code": key[1],
            "marketplace": key[2],
            "currency": key[3],
            "asin": key[4],
            "sku": key[5],
            "title": key[6],
            "report_type": key[7],
        }

    @staticmethod
    def _parse_date(value: str) -> date:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except Exception as exc:
            raise ValueError("date must be in YYYY-MM-DD format") from exc

    @staticmethod
    def _date_str(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

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
