"""Sales & Traffic ingestion for Revenue Intelligence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from database import SessionLocal
from models import SellerCentralSalesTraffic


class SalesTrafficIngestionService:
    version = "8.8"

    @staticmethod
    def ingest_payload(
        payload: dict[str, Any] | list[Any],
        country_code: str | None = None,
        marketplace: str | None = None,
        marketplace_id: str | None = None,
        currency: str | None = None,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        rows = SalesTrafficIngestionService._extract_rows(payload)
        db = SessionLocal()
        inserted = 0
        skipped = 0
        try:
            for item in rows:
                normalized = SalesTrafficIngestionService._normalize_row(
                    item,
                    country_code=country_code,
                    marketplace=marketplace,
                    currency=currency,
                    profile_id=profile_id,
                )
                if not normalized.get("date"):
                    skipped += 1
                    continue
                db.add(SellerCentralSalesTraffic(**normalized, raw=item))
                inserted += 1
            db.commit()
            return {
                "status": "OK",
                "version": SalesTrafficIngestionService.version,
                "rows_seen": len(rows),
                "rows_inserted": inserted,
                "rows_skipped": skipped,
                "marketplace_id": marketplace_id,
                "message": "Sales & Traffic rows ingested into seller_central_sales_traffic.",
            }
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": SalesTrafficIngestionService.version, "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def _extract_rows(payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]
        if not isinstance(payload, dict):
            return []
        candidates = []
        # SP-API Sales & Traffic reports commonly contain salesAndTrafficByAsin
        # and/or salesAndTrafficByDate arrays.
        for key in ["salesAndTrafficByAsin", "salesAndTrafficByDate", "rows", "data"]:
            value = payload.get(key)
            if isinstance(value, list):
                candidates.extend([x for x in value if isinstance(x, dict)])
        if candidates:
            return candidates
        return [payload]

    @staticmethod
    def _normalize_row(
        row: dict[str, Any],
        country_code: str | None,
        marketplace: str | None,
        currency: str | None,
        profile_id: str | None,
    ) -> dict[str, Any]:
        asin = row.get("childAsin") or row.get("parentAsin") or row.get("asin")
        sku = row.get("sku") or row.get("sellerSku")
        title = row.get("title") or row.get("productName")
        date_value = row.get("date") or row.get("startDate") or row.get("reportDate")
        sales_by_asin = row.get("salesByAsin") if isinstance(row.get("salesByAsin"), dict) else {}
        traffic_by_asin = row.get("trafficByAsin") if isinstance(row.get("trafficByAsin"), dict) else {}
        sales_by_date = row.get("salesByDate") if isinstance(row.get("salesByDate"), dict) else {}
        traffic_by_date = row.get("trafficByDate") if isinstance(row.get("trafficByDate"), dict) else {}
        sales = {**sales_by_date, **sales_by_asin, **row}
        traffic = {**traffic_by_date, **traffic_by_asin, **row}
        return {
            "date": SalesTrafficIngestionService._parse_date(date_value),
            "channel": "amazon",
            "profile_id": profile_id,
            "country_code": (country_code or row.get("country_code") or row.get("countryCode") or "").upper() or None,
            "marketplace": marketplace or row.get("marketplace"),
            "currency": currency or SalesTrafficIngestionService._currency_from_sales(sales),
            "asin": asin,
            "sku": sku,
            "title": title,
            "ordered_product_sales": SalesTrafficIngestionService._money(sales.get("orderedProductSales")),
            "units_ordered": SalesTrafficIngestionService._int(sales.get("unitsOrdered")),
            "total_order_items": SalesTrafficIngestionService._int(sales.get("totalOrderItems")),
            "sessions": SalesTrafficIngestionService._int(traffic.get("sessions")),
            "page_views": SalesTrafficIngestionService._int(traffic.get("pageViews")),
            "buy_box_percentage": SalesTrafficIngestionService._float(traffic.get("buyBoxPercentage")),
            "unit_session_percentage": SalesTrafficIngestionService._float(traffic.get("unitSessionPercentage")),
            "report_type": "GET_SALES_AND_TRAFFIC_REPORT",
        }

    @staticmethod
    def _parse_date(value: Any):
        if not value:
            return None
        text = str(value)[:10]
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except Exception:
            return None

    @staticmethod
    def _currency_from_sales(value: dict[str, Any]) -> str | None:
        money = value.get("orderedProductSales")
        if isinstance(money, dict):
            return money.get("currencyCode")
        return None

    @staticmethod
    def _money(value: Any) -> float:
        if isinstance(value, dict):
            value = value.get("amount")
        return SalesTrafficIngestionService._float(value)

    @staticmethod
    def _float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value if value is not None else default)
        except Exception:
            return default

    @staticmethod
    def _int(value: Any, default: int = 0) -> int:
        try:
            return int(float(value if value is not None else default))
        except Exception:
            return default
