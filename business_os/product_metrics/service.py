
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import inspect, text

from database import SessionLocal, engine
from business_registry.models import MasterProduct


class ProductMetricsService:
    version = "business-os-0.6.3"

    CAMPAIGN_TABLES = ["campaign_daily_details", "campaign_reports", "campaign_performance"]
    SALES_TABLES = ["sales_daily_details", "order_daily_details", "seller_sales_daily_details", "orders_daily_details"]

    @classmethod
    def metrics(cls, master_product_id: str, days: int = 30) -> dict[str, Any]:
        db = SessionLocal()
        try:
            product = db.query(MasterProduct).filter(MasterProduct.master_product_id == master_product_id).first()
            if not product:
                return {"status": "NOT_FOUND", "version": cls.version, "master_product_id": master_product_id}

            days = max(1, min(days, 365))
            start_date = date.today() - timedelta(days=days)

            ad = cls._ad_metrics(db, master_product_id, start_date)
            sales = cls._sales_metrics(db, master_product_id, start_date)

            ad_sales = float(ad.get("ad_sales") or 0)
            spend = float(ad.get("spend") or 0)
            total_sales = sales.get("total_sales")
            if total_sales is None:
                total_sales = ad_sales
            total_sales = float(total_sales or 0)

            organic_sales = max(0, total_sales - ad_sales)
            acos = spend / ad_sales if ad_sales else None
            tacos = spend / total_sales if total_sales else None
            organic_ratio = organic_sales / total_sales if total_sales else None
            paid_ratio = ad_sales / total_sales if total_sales else None
            clicks = float(ad.get("clicks") or 0)
            orders = float(sales.get("orders") if sales.get("orders") is not None else ad.get("orders") or 0)

            return {
                "status": "OK",
                "version": cls.version,
                "master_product_id": master_product_id,
                "product_name": product.name,
                "days": days,
                "metrics": {
                    "sales_30d": round(total_sales, 2),
                    "organic_sales_30d": round(organic_sales, 2),
                    "ad_sales_30d": round(ad_sales, 2),
                    "spend_30d": round(spend, 2),
                    "acos": round(acos, 4) if acos is not None else None,
                    "acos_pct": round(acos * 100, 2) if acos is not None else None,
                    "tacos": round(tacos, 4) if tacos is not None else None,
                    "tacos_pct": round(tacos * 100, 2) if tacos is not None else None,
                    "organic_ratio": round(organic_ratio, 4) if organic_ratio is not None else None,
                    "organic_ratio_pct": round(organic_ratio * 100, 2) if organic_ratio is not None else None,
                    "paid_ratio": round(paid_ratio, 4) if paid_ratio is not None else None,
                    "paid_ratio_pct": round(paid_ratio * 100, 2) if paid_ratio is not None else None,
                    "orders_30d": int(orders),
                    "clicks_30d": int(clicks),
                    "impressions_30d": int(ad.get("impressions") or 0),
                    "conversion_rate": round(orders / clicks, 4) if clicks else None,
                    "conversion_rate_pct": round((orders / clicks) * 100, 2) if clicks else None,
                    "roas": round(ad_sales / spend, 2) if spend else None,
                    "profit_30d": None,
                    "margin_pct": None,
                    "data_quality": {
                        "has_ad_data": bool(ad.get("source_table")),
                        "has_sales_data": bool(sales.get("source_table") and sales.get("total_sales") is not None),
                        "ad_source_note": ad.get("note"),
                        "sales_source_note": sales.get("note"),
                    },
                    "sources": {
                        "advertising": ad.get("source_table"),
                        "sales": sales.get("source_table"),
                    },
                },
            }
        finally:
            db.close()

    @classmethod
    def trend(cls, master_product_id: str, days: int = 30) -> dict[str, Any]:
        db = SessionLocal()
        try:
            days = max(7, min(days, 365))
            start_date = date.today() - timedelta(days=days)
            return {
                "status": "OK",
                "version": cls.version,
                "master_product_id": master_product_id,
                "days": days,
                "trend": cls._daily_ad_rows(db, master_product_id, start_date),
            }
        finally:
            db.close()

    @classmethod
    def portfolio_metrics(cls, limit: int = 250) -> dict[str, Any]:
        db = SessionLocal()
        try:
            products = db.query(MasterProduct).filter(MasterProduct.active == True).limit(max(1, min(limit, 500))).all()
            items = []
            for product in products:
                result = cls.metrics(product.master_product_id)
                if result.get("status") == "OK":
                    m = result.get("metrics", {})
                    items.append({
                        "master_product_id": product.master_product_id,
                        "product_name": product.name,
                        "sales_30d": m.get("sales_30d"),
                        "ad_sales_30d": m.get("ad_sales_30d"),
                        "spend_30d": m.get("spend_30d"),
                        "acos_pct": m.get("acos_pct"),
                        "tacos_pct": m.get("tacos_pct"),
                        "organic_ratio_pct": m.get("organic_ratio_pct"),
                    })
            return {
                "status": "OK",
                "version": cls.version,
                "count": len(items),
                "summary": {
                    "sales_30d": round(sum(i.get("sales_30d") or 0 for i in items), 2),
                    "ad_sales_30d": round(sum(i.get("ad_sales_30d") or 0 for i in items), 2),
                    "spend_30d": round(sum(i.get("spend_30d") or 0 for i in items), 2),
                },
                "products": items,
            }
        finally:
            db.close()

    @classmethod
    def _ad_metrics(cls, db, master_product_id: str, start_date: date) -> dict[str, Any]:
        table = cls._first_existing_table(cls.CAMPAIGN_TABLES)
        if not table:
            return {"source_table": None, "spend": 0, "ad_sales": 0, "orders": 0, "clicks": 0, "impressions": 0}

        cols = cls._columns(table)
        if "master_product_id" not in cols:
            return {"source_table": table, "spend": 0, "ad_sales": 0, "orders": 0, "clicks": 0, "impressions": 0, "note": "missing master_product_id"}

        return cls._sum_table(
            db=db,
            table=table,
            master_product_id=master_product_id,
            start_date=start_date,
            date_col=cls._find_col(cols, ["date", "report_date", "startDate", "created_at"]),
            mapping={
                "spend": cls._find_col(cols, ["spend", "cost"]),
                "ad_sales": cls._find_col(cols, ["sales", "sales7d", "attributedSales7d", "totalSales"]),
                "orders": cls._find_col(cols, ["orders", "purchases7d", "attributedConversions7d", "conversions"]),
                "clicks": cls._find_col(cols, ["clicks"]),
                "impressions": cls._find_col(cols, ["impressions"]),
            },
        )

    @classmethod
    def _sales_metrics(cls, db, master_product_id: str, start_date: date) -> dict[str, Any]:
        table = cls._first_existing_table(cls.SALES_TABLES)
        if not table:
            return {"source_table": None, "total_sales": None, "orders": None}

        cols = cls._columns(table)
        if "master_product_id" not in cols:
            return {"source_table": table, "total_sales": None, "orders": None, "note": "missing master_product_id"}

        return cls._sum_table(
            db=db,
            table=table,
            master_product_id=master_product_id,
            start_date=start_date,
            date_col=cls._find_col(cols, ["date", "order_date", "purchase_date", "report_date", "created_at"]),
            mapping={
                "total_sales": cls._find_col(cols, ["sales", "revenue", "total_sales", "gross_sales", "ordered_product_sales"]),
                "orders": cls._find_col(cols, ["orders", "order_count", "units_ordered", "quantity"]),
            },
        )

    @classmethod
    def _sum_table(cls, db, table: str, master_product_id: str, start_date: date, date_col: str | None, mapping: dict[str, str | None]) -> dict[str, Any]:
        select_parts = []
        for alias, col in mapping.items():
            if col:
                select_parts.append(f'COALESCE(SUM(CAST("{col}" AS FLOAT)), 0) AS "{alias}"')
            else:
                select_parts.append(f'0 AS "{alias}"')

        where = ['master_product_id = :mpid']
        params = {"mpid": master_product_id}
        if date_col:
            where.append(f'"{date_col}" >= :start_date')
            params["start_date"] = str(start_date)

        sql = f'SELECT {", ".join(select_parts)} FROM "{table}" WHERE {" AND ".join(where)}'
        row = db.execute(text(sql), params).mappings().first()
        output = dict(row or {})
        output["source_table"] = table
        return output

    @classmethod
    def _daily_ad_rows(cls, db, master_product_id: str, start_date: date) -> list[dict[str, Any]]:
        table = cls._first_existing_table(cls.CAMPAIGN_TABLES)
        if not table:
            return []
        cols = cls._columns(table)
        if "master_product_id" not in cols:
            return []

        date_col = cls._find_col(cols, ["date", "report_date", "startDate", "created_at"])
        spend_col = cls._find_col(cols, ["spend", "cost"])
        sales_col = cls._find_col(cols, ["sales", "sales7d", "attributedSales7d", "totalSales"])
        orders_col = cls._find_col(cols, ["orders", "purchases7d", "attributedConversions7d", "conversions"])
        if not date_col or not spend_col or not sales_col or not orders_col:
            return []

        sql = f'''
            SELECT
                "{date_col}" AS date,
                COALESCE(SUM(CAST("{spend_col}" AS FLOAT)), 0) AS spend,
                COALESCE(SUM(CAST("{sales_col}" AS FLOAT)), 0) AS ad_sales,
                COALESCE(SUM(CAST("{orders_col}" AS FLOAT)), 0) AS orders
            FROM "{table}"
            WHERE master_product_id = :mpid AND "{date_col}" >= :start_date
            GROUP BY "{date_col}"
            ORDER BY "{date_col}"
        '''
        rows = db.execute(text(sql), {"mpid": master_product_id, "start_date": str(start_date)}).mappings().all()
        output = []
        for row in rows:
            spend = float(row.get("spend") or 0)
            ad_sales = float(row.get("ad_sales") or 0)
            output.append({
                "date": str(row.get("date")),
                "spend": round(spend, 2),
                "ad_sales": round(ad_sales, 2),
                "orders": int(float(row.get("orders") or 0)),
                "acos_pct": round((spend / ad_sales) * 100, 2) if ad_sales else None,
            })
        return output

    @staticmethod
    def _first_existing_table(tables: list[str]) -> str | None:
        inspector = inspect(engine)
        for table in tables:
            if inspector.has_table(table):
                return table
        return None

    @staticmethod
    def _columns(table: str) -> list[str]:
        return [c["name"] for c in inspect(engine).get_columns(table)]

    @staticmethod
    def _find_col(cols: list[str], candidates: list[str]) -> str | None:
        lower = {c.lower(): c for c in cols}
        for candidate in candidates:
            if candidate in cols:
                return candidate
            if candidate.lower() in lower:
                return lower[candidate.lower()]
        return None
