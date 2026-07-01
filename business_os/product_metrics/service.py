"""Business OS v0.6.5 — Product Metrics Service.

Adds Product Performance Mix:
- Uses advertising rows when available.
- Detects Seller/SP-API product sales tables dynamically when present.
- Computes total, paid, and organic sales mix without requiring a migration.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import inspect, text

from database import SessionLocal, engine
from business_registry.models import MasterProduct


class ProductMetricsService:
    version = "business-os-0.6.5"

    CAMPAIGN_TABLE = "campaign_daily_details"
    SEARCH_TABLE = "search_term_daily_details"
    SELLER_TABLE_CANDIDATES = [
        "seller_product_daily_details",
        "seller_sales_daily_details",
        "sp_api_product_daily_details",
        "product_sales_daily_details",
        "revenue_daily_details",
    ]

    @classmethod
    def product_metrics(cls, master_product_id: str, days: int = 30) -> dict[str, Any]:
        db = SessionLocal()
        try:
            product = db.query(MasterProduct).filter(MasterProduct.master_product_id == master_product_id).first()
            if not product:
                return {"status": "NOT_FOUND", "version": cls.version, "master_product_id": master_product_id}

            ad_rows = cls._rows_for_product(db, cls.CAMPAIGN_TABLE, master_product_id, days)
            search_rows = cls._rows_for_product(db, cls.SEARCH_TABLE, master_product_id, days)
            seller_rows, seller_table = cls._seller_rows_for_product(db, master_product_id, days)

            ad_totals = cls._totals(ad_rows)
            search_totals = cls._totals(search_rows)
            seller_totals = cls._seller_totals(seller_rows)

            spend = ad_totals["spend"] if ad_rows else search_totals["spend"]
            ad_sales = ad_totals["sales"] if ad_rows else search_totals["sales"]
            ad_orders = ad_totals["orders"] if ad_rows else search_totals["orders"]
            clicks = ad_totals["clicks"] if ad_rows else search_totals["clicks"]
            impressions = ad_totals["impressions"] if ad_rows else search_totals["impressions"]

            seller_sales = seller_totals["sales"]
            seller_orders = seller_totals["orders"]
            seller_units = seller_totals["units"]

            has_seller_sales = seller_sales > 0 or seller_orders > 0 or seller_units > 0
            sales = seller_sales if has_seller_sales else ad_sales
            orders = seller_orders if seller_orders > 0 else ad_orders
            organic_sales = max(sales - ad_sales, 0.0) if has_seller_sales else None
            organic_orders = max(seller_orders - ad_orders, 0.0) if seller_orders > 0 else None

            acos = spend / ad_sales if ad_sales else None
            roas = ad_sales / spend if spend else None
            ctr = clicks / impressions if impressions else None
            conversion_rate = ad_orders / clicks if clicks else None
            tacos = spend / sales if sales else None
            paid_sales_share = ad_sales / sales if sales else None
            organic_sales_share = organic_sales / sales if organic_sales is not None and sales else None

            trend = cls._trend(db, cls.CAMPAIGN_TABLE, master_product_id, days) if cls._table_ready(cls.CAMPAIGN_TABLE) else []
            mix_trend = cls._performance_mix_trend(db, master_product_id, days)

            return {
                "status": "OK",
                "version": cls.version,
                "master_product_id": master_product_id,
                "product_name": product.name,
                "window_days": days,
                "metrics": {
                    "sales_30d": round(sales, 2),
                    "organic_sales_30d": round(organic_sales, 2) if organic_sales is not None else None,
                    "ad_sales_30d": round(ad_sales, 2),
                    "spend_30d": round(spend, 2),
                    "acos": round(acos, 4) if acos is not None else None,
                    "acos_pct": round(acos * 100, 2) if acos is not None else None,
                    "tacos": round(tacos, 4) if tacos is not None else None,
                    "tacos_pct": round(tacos * 100, 2) if tacos is not None else None,
                    "roas": round(roas, 2) if roas is not None else None,
                    "orders_30d": int(orders),
                    "ad_orders_30d": int(ad_orders),
                    "organic_orders_30d": int(organic_orders) if organic_orders is not None else None,
                    "seller_units_30d": int(seller_units) if seller_units else None,
                    "clicks_30d": int(clicks),
                    "impressions_30d": int(impressions),
                    "ctr": round(ctr, 4) if ctr is not None else None,
                    "ctr_pct": round(ctr * 100, 2) if ctr is not None else None,
                    "conversion_rate": round(conversion_rate, 4) if conversion_rate is not None else None,
                    "conversion_rate_pct": round(conversion_rate * 100, 2) if conversion_rate is not None else None,
                    "paid_sales_share": round(paid_sales_share, 4) if paid_sales_share is not None else None,
                    "paid_sales_share_pct": round(paid_sales_share * 100, 2) if paid_sales_share is not None else None,
                    "organic_sales_share": round(organic_sales_share, 4) if organic_sales_share is not None else None,
                    "organic_sales_share_pct": round(organic_sales_share * 100, 2) if organic_sales_share is not None else None,
                    "advertising_dependency_pct": round(paid_sales_share * 100, 2) if paid_sales_share is not None else None,
                    "profit_30d": None,
                    "margin_pct": None,
                },
                "performance_mix": {
                    "total_sales_30d": round(sales, 2),
                    "ad_sales_30d": round(ad_sales, 2),
                    "organic_sales_30d": round(organic_sales, 2) if organic_sales is not None else None,
                    "paid_sales_share_pct": round(paid_sales_share * 100, 2) if paid_sales_share is not None else None,
                    "organic_sales_share_pct": round(organic_sales_share * 100, 2) if organic_sales_share is not None else None,
                    "advertising_dependency_pct": round(paid_sales_share * 100, 2) if paid_sales_share is not None else None,
                    "seller_sales_available": has_seller_sales,
                    "seller_source_table": seller_table,
                    "interpretation": cls._mix_interpretation(has_seller_sales, paid_sales_share, organic_sales_share),
                },
                "data_quality": {
                    "campaign_rows": len(ad_rows),
                    "search_rows": len(search_rows),
                    "seller_rows": len(seller_rows),
                    "seller_source_table": seller_table,
                    "organic_sales_available": has_seller_sales,
                    "profit_available": False,
                    "notes": cls._data_quality_notes(has_seller_sales),
                },
                "trend": trend,
                "performance_mix_trend": mix_trend,
            }
        finally:
            db.close()

    @classmethod
    def portfolio_metrics(cls, limit: int = 250) -> dict[str, Any]:
        db = SessionLocal()
        try:
            products = db.query(MasterProduct).filter(MasterProduct.active == True).limit(max(1, min(limit, 500))).all()
            rows = []
            for product in products:
                item = cls.product_metrics(product.master_product_id)
                if item.get("status") == "OK":
                    rows.append({
                        "master_product_id": product.master_product_id,
                        "product_name": product.name,
                        **item.get("metrics", {}),
                    })

            spend = sum(r.get("spend_30d") or 0 for r in rows)
            total_sales = sum(r.get("sales_30d") or 0 for r in rows)
            ad_sales = sum(r.get("ad_sales_30d") or 0 for r in rows)
            organic_sales_values = [r.get("organic_sales_30d") for r in rows if r.get("organic_sales_30d") is not None]
            organic_sales = sum(organic_sales_values) if organic_sales_values else None
            orders = sum(r.get("orders_30d") or 0 for r in rows)

            return {
                "status": "OK",
                "version": cls.version,
                "count": len(rows),
                "summary": {
                    "sales_30d": round(total_sales, 2),
                    "ad_sales_30d": round(ad_sales, 2),
                    "organic_sales_30d": round(organic_sales, 2) if organic_sales is not None else None,
                    "spend_30d": round(spend, 2),
                    "orders_30d": int(orders),
                    "portfolio_acos_pct": round((spend / ad_sales) * 100, 2) if ad_sales else None,
                    "portfolio_tacos_pct": round((spend / total_sales) * 100, 2) if total_sales else None,
                    "paid_sales_share_pct": round((ad_sales / total_sales) * 100, 2) if total_sales else None,
                    "organic_sales_share_pct": round((organic_sales / total_sales) * 100, 2) if organic_sales is not None and total_sales else None,
                    "products_with_seller_sales": len([r for r in rows if r.get("organic_sales_30d") is not None]),
                },
                "products": rows,
            }
        finally:
            db.close()

    @classmethod
    def _rows_for_product(cls, db, table: str, master_product_id: str, days: int) -> list[dict[str, Any]]:
        if not cls._table_ready(table):
            return []

        cols = cls._columns(table)
        select_cols = ", ".join([f'"{c}"' for c in cols])
        date_col = cls._date_column(cols)
        where = 'master_product_id = :mpid'
        params = {"mpid": master_product_id}

        if date_col:
            start = date.today() - timedelta(days=days)
            where += f' AND "{date_col}" >= :start_date'
            params["start_date"] = str(start)

        sql = f'SELECT {select_cols} FROM "{table}" WHERE {where} LIMIT 20000'
        return [dict(row) for row in db.execute(text(sql), params).mappings().all()]

    @classmethod
    def _seller_rows_for_product(cls, db, master_product_id: str, days: int) -> tuple[list[dict[str, Any]], str | None]:
        for table in cls.SELLER_TABLE_CANDIDATES:
            rows = cls._rows_for_product(db, table, master_product_id, days)
            if rows:
                return rows, table
        return [], None

    @classmethod
    def _totals(cls, rows: list[dict[str, Any]]) -> dict[str, float]:
        totals = {"spend": 0.0, "sales": 0.0, "orders": 0.0, "clicks": 0.0, "impressions": 0.0}
        for row in rows:
            raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
            totals["spend"] += cls._num(cls._first(row, raw, ["spend", "cost"]))
            totals["sales"] += cls._num(cls._first(row, raw, ["sales", "sales7d", "attributedSales7d", "totalSales"]))
            totals["orders"] += cls._num(cls._first(row, raw, ["orders", "purchases7d", "attributedConversions7d", "conversions"]))
            totals["clicks"] += cls._num(cls._first(row, raw, ["clicks"]))
            totals["impressions"] += cls._num(cls._first(row, raw, ["impressions"]))
        return totals

    @classmethod
    def _seller_totals(cls, rows: list[dict[str, Any]]) -> dict[str, float]:
        totals = {"sales": 0.0, "orders": 0.0, "units": 0.0}
        for row in rows:
            raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
            totals["sales"] += cls._num(cls._first(row, raw, [
                "ordered_product_sales", "orderedProductSales", "total_sales", "totalSales", "sales", "revenue", "gross_sales"
            ]))
            totals["orders"] += cls._num(cls._first(row, raw, [
                "orders", "total_orders", "order_count", "ordered_units", "orderedUnits", "units_ordered"
            ]))
            totals["units"] += cls._num(cls._first(row, raw, [
                "units", "units_ordered", "ordered_units", "orderedUnits", "quantity"
            ]))
        return totals

    @classmethod
    def _trend(cls, db, table: str, master_product_id: str, days: int) -> list[dict[str, Any]]:
        cols = cls._columns(table)
        date_col = cls._date_column(cols)
        if not date_col:
            return []

        rows = cls._rows_for_product(db, table, master_product_id, days)
        by_date: dict[str, dict[str, float]] = {}

        for row in rows:
            day = str(row.get(date_col))[:10]
            raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
            item = by_date.setdefault(day, {"date": day, "spend": 0.0, "sales": 0.0, "orders": 0.0})
            item["spend"] += cls._num(cls._first(row, raw, ["spend", "cost"]))
            item["sales"] += cls._num(cls._first(row, raw, ["sales", "sales7d", "attributedSales7d", "totalSales"]))
            item["orders"] += cls._num(cls._first(row, raw, ["orders", "purchases7d", "attributedConversions7d", "conversions"]))

        output = []
        for day in sorted(by_date):
            item = by_date[day]
            item["acos_pct"] = round((item["spend"] / item["sales"]) * 100, 2) if item["sales"] else None
            item["spend"] = round(item["spend"], 2)
            item["sales"] = round(item["sales"], 2)
            output.append(item)
        return output

    @classmethod
    def _performance_mix_trend(cls, db, master_product_id: str, days: int) -> list[dict[str, Any]]:
        ad_trend = cls._trend(db, cls.CAMPAIGN_TABLE, master_product_id, days) if cls._table_ready(cls.CAMPAIGN_TABLE) else []
        seller_rows, _seller_table = cls._seller_rows_for_product(db, master_product_id, days)
        if not seller_rows:
            return []

        seller_by_date: dict[str, float] = {}
        seller_cols = list(seller_rows[0].keys()) if seller_rows else []
        seller_date_col = cls._date_column(seller_cols)
        for row in seller_rows:
            if not seller_date_col:
                continue
            day = str(row.get(seller_date_col))[:10]
            raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
            seller_by_date[day] = seller_by_date.get(day, 0.0) + cls._num(cls._first(row, raw, [
                "ordered_product_sales", "orderedProductSales", "total_sales", "totalSales", "sales", "revenue", "gross_sales"
            ]))

        ad_by_date = {row.get("date"): row for row in ad_trend}
        output = []
        for day in sorted(set(seller_by_date) | set(ad_by_date)):
            total_sales = seller_by_date.get(day) or ad_by_date.get(day, {}).get("sales") or 0.0
            ad_sales = ad_by_date.get(day, {}).get("sales") or 0.0
            organic_sales = max(total_sales - ad_sales, 0.0) if total_sales else None
            output.append({
                "date": day,
                "sales": round(total_sales, 2),
                "ad_sales": round(ad_sales, 2),
                "organic_sales": round(organic_sales, 2) if organic_sales is not None else None,
                "paid_sales_share_pct": round((ad_sales / total_sales) * 100, 2) if total_sales else None,
                "organic_sales_share_pct": round((organic_sales / total_sales) * 100, 2) if organic_sales is not None and total_sales else None,
            })
        return output

    @staticmethod
    def _mix_interpretation(has_seller_sales: bool, paid_share: float | None, organic_share: float | None) -> str:
        if not has_seller_sales:
            return "Seller Central/SP-API product sales are not available yet, so total sales currently equal attributed ad sales. Organic-vs-paid split is not computed."
        if paid_share is None:
            return "Seller sales are available, but paid sales share could not be calculated."
        if paid_share >= 0.8:
            return "This product appears highly advertising-dependent. Prioritize organic rank, listing conversion, and exact-match efficiency."
        if paid_share >= 0.45:
            return "This product has a balanced paid/organic mix. Optimize ads while continuing to improve organic visibility."
        return "This product appears organically strong relative to ad-attributed sales. Protect ranking and use ads selectively for growth."

    @staticmethod
    def _data_quality_notes(has_seller_sales: bool) -> list[str]:
        notes = []
        if has_seller_sales:
            notes.append("Organic sales are estimated as Seller/SP-API total sales minus attributed ad sales.")
            notes.append("TACOS uses Seller/SP-API total sales when available.")
        else:
            notes.append("Organic sales require Seller Central/SP-API product sales ingestion.")
            notes.append("Until seller sales are available, sales_30d is ad-attributed sales only.")
        notes.append("Profit requires COGS, fees, shipping, and refunds.")
        return notes

    @staticmethod
    def _table_ready(table: str) -> bool:
        try:
            if not inspect(engine).has_table(table):
                return False
            cols = [c["name"] for c in inspect(engine).get_columns(table)]
            return "master_product_id" in cols
        except Exception:
            return False

    @staticmethod
    def _columns(table: str) -> list[str]:
        return [c["name"] for c in inspect(engine).get_columns(table)]

    @staticmethod
    def _date_column(cols: list[str]) -> str | None:
        for c in ["date", "report_date", "startDate", "created_at", "snapshot_date"]:
            if c in cols:
                return c
        return None

    @staticmethod
    def _first(row: dict[str, Any], raw: dict[str, Any], names: list[str]) -> Any:
        for name in names:
            if row.get(name) is not None:
                return row.get(name)
            if raw.get(name) is not None:
                return raw.get(name)
        row_lower = {str(k).lower(): v for k, v in row.items()}
        raw_lower = {str(k).lower(): v for k, v in raw.items()}
        for name in names:
            key = name.lower()
            if row_lower.get(key) is not None:
                return row_lower.get(key)
            if raw_lower.get(key) is not None:
                return raw_lower.get(key)
        return None

    @staticmethod
    def _num(value: Any) -> float:
        if value is None:
            return 0.0
        try:
            if isinstance(value, str):
                return float(value.replace("$", "").replace(",", "").replace("%", "").strip())
            return float(value)
        except Exception:
            return 0.0
