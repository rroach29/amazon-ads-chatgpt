"""Business OS v0.6.4 — Product Metrics Service."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import inspect, text

from database import SessionLocal, engine
from business_registry.models import MasterProduct


class ProductMetricsService:
    version = "business-os-0.6.4"

    CAMPAIGN_TABLE = "campaign_daily_details"
    SEARCH_TABLE = "search_term_daily_details"

    @classmethod
    def product_metrics(cls, master_product_id: str, days: int = 30) -> dict[str, Any]:
        db = SessionLocal()
        try:
            product = db.query(MasterProduct).filter(MasterProduct.master_product_id == master_product_id).first()
            if not product:
                return {"status": "NOT_FOUND", "version": cls.version, "master_product_id": master_product_id}

            ad_rows = cls._rows_for_product(db, cls.CAMPAIGN_TABLE, master_product_id, days)
            search_rows = cls._rows_for_product(db, cls.SEARCH_TABLE, master_product_id, days)

            ad_totals = cls._totals(ad_rows)
            search_totals = cls._totals(search_rows)

            spend = ad_totals["spend"] if ad_rows else search_totals["spend"]
            ad_sales = ad_totals["sales"] if ad_rows else search_totals["sales"]
            sales = ad_sales
            orders = ad_totals["orders"] if ad_rows else search_totals["orders"]
            clicks = ad_totals["clicks"] if ad_rows else search_totals["clicks"]
            impressions = ad_totals["impressions"] if ad_rows else search_totals["impressions"]

            acos = spend / ad_sales if ad_sales else None
            roas = ad_sales / spend if spend else None
            ctr = clicks / impressions if impressions else None
            conversion_rate = orders / clicks if clicks else None
            tacos = spend / sales if sales else None

            trend = cls._trend(db, cls.CAMPAIGN_TABLE, master_product_id, days) if cls._table_ready(cls.CAMPAIGN_TABLE) else []

            return {
                "status": "OK",
                "version": cls.version,
                "master_product_id": master_product_id,
                "product_name": product.name,
                "window_days": days,
                "metrics": {
                    "sales_30d": round(sales, 2),
                    "organic_sales_30d": None,
                    "ad_sales_30d": round(ad_sales, 2),
                    "spend_30d": round(spend, 2),
                    "acos": round(acos, 4) if acos is not None else None,
                    "acos_pct": round(acos * 100, 2) if acos is not None else None,
                    "tacos": round(tacos, 4) if tacos is not None else None,
                    "tacos_pct": round(tacos * 100, 2) if tacos is not None else None,
                    "roas": round(roas, 2) if roas is not None else None,
                    "orders_30d": int(orders),
                    "clicks_30d": int(clicks),
                    "impressions_30d": int(impressions),
                    "ctr": round(ctr, 4) if ctr is not None else None,
                    "ctr_pct": round(ctr * 100, 2) if ctr is not None else None,
                    "conversion_rate": round(conversion_rate, 4) if conversion_rate is not None else None,
                    "conversion_rate_pct": round(conversion_rate * 100, 2) if conversion_rate is not None else None,
                    "profit_30d": None,
                    "margin_pct": None,
                },
                "data_quality": {
                    "campaign_rows": len(ad_rows),
                    "search_rows": len(search_rows),
                    "organic_sales_available": False,
                    "profit_available": False,
                    "notes": [
                        "Organic sales require Seller Central integration.",
                        "Profit requires COGS, fees, shipping, and refunds.",
                    ],
                },
                "trend": trend,
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
            sales = sum(r.get("ad_sales_30d") or 0 for r in rows)
            orders = sum(r.get("orders_30d") or 0 for r in rows)

            return {
                "status": "OK",
                "version": cls.version,
                "count": len(rows),
                "summary": {
                    "sales_30d": round(sales, 2),
                    "ad_sales_30d": round(sales, 2),
                    "spend_30d": round(spend, 2),
                    "orders_30d": int(orders),
                    "portfolio_acos_pct": round((spend / sales) * 100, 2) if sales else None,
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
        for c in ["date", "report_date", "startDate", "created_at"]:
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
