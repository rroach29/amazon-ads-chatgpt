"""Sales & Traffic ingestion for Revenue Intelligence.

v9.0.7 changes:
- Idempotent import: before inserting normalized Sales & Traffic rows, remove
  existing rows for the same date + canonical marketplace + report type.
- Prevents repeated Swagger testing from duplicating Seller Central revenue/orders.
- Skips unknown aggregate rows when marketplace/country context is supplied.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from database import SessionLocal
from models import SellerCentralSalesTraffic


class SalesTrafficIngestionService:
    version = "9.0.7"

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
        normalized_rows = []
        skipped = 0

        for item in rows:
            normalized = SalesTrafficIngestionService._normalize_row(
                item,
                country_code=country_code,
                marketplace=marketplace,
                marketplace_id=marketplace_id,
                currency=currency,
                profile_id=profile_id,
            )
            if not normalized.get("date"):
                skipped += 1
                continue
            if SalesTrafficIngestionService._is_unknown_aggregate(normalized) and (country_code or marketplace or marketplace_id):
                skipped += 1
                continue
            normalized_rows.append((normalized, item))

        db = SessionLocal()
        inserted = 0
        deleted_existing = 0
        try:
            # Idempotency: delete only the exact date + canonical marketplace
            # scopes represented in this payload before inserting replacement rows.
            scopes = set()
            for normalized, _raw in normalized_rows:
                scopes.add(
                    (
                        normalized.get("date"),
                        *SalesTrafficIngestionService._canonical_market_key(
                            normalized.get("country_code"),
                            normalized.get("marketplace"),
                            normalized.get("currency"),
                        ),
                        normalized.get("report_type") or "GET_SALES_AND_TRAFFIC_REPORT",
                    )
                )

            for report_date, canon_country, canon_marketplace, canon_currency, report_type in scopes:
                existing = (
                    db.query(SellerCentralSalesTraffic)
                    .filter(SellerCentralSalesTraffic.date == report_date)
                    .filter(SellerCentralSalesTraffic.report_type == report_type)
                    .all()
                )
                for row in existing:
                    row_country, row_marketplace, row_currency = SalesTrafficIngestionService._canonical_market_key(
                        row.country_code,
                        row.marketplace,
                        row.currency,
                    )
                    if (
                        row_country == canon_country
                        and row_marketplace == canon_marketplace
                        and row_currency == canon_currency
                    ):
                        db.delete(row)
                        deleted_existing += 1
                db.flush()

            for normalized, raw in normalized_rows:
                db.add(SellerCentralSalesTraffic(**normalized, raw=raw))
                inserted += 1

            db.commit()
            return {
                "status": "OK",
                "version": SalesTrafficIngestionService.version,
                "rows_seen": len(rows),
                "rows_inserted": inserted,
                "rows_skipped": skipped,
                "existing_rows_deleted_for_idempotency": deleted_existing,
                "marketplace_id": marketplace_id,
                "idempotency": {
                    "enabled": True,
                    "scope": "date + canonical marketplace + currency + report_type",
                    "note": "Re-importing the same report/date/marketplace now replaces rows instead of duplicating them.",
                },
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
        # Prefer ASIN detail rows where present. If the report only contains date
        # totals, those are used. Do not combine detail and totals as additive
        # views when both exist.
        for key in ["salesAndTrafficByAsin", "rows", "data"]:
            value = payload.get(key)
            if isinstance(value, list) and value:
                candidates.extend([x for x in value if isinstance(x, dict)])
                return candidates
        value = payload.get("salesAndTrafficByDate")
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
        marketplace_id: str | None,
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

        resolved_country, resolved_marketplace, resolved_currency = SalesTrafficIngestionService._canonical_market_key(
            country_code or row.get("country_code") or row.get("countryCode") or marketplace_id,
            marketplace or row.get("marketplace") or marketplace_id,
            currency or SalesTrafficIngestionService._currency_from_sales(sales),
        )

        return {
            "date": SalesTrafficIngestionService._parse_date(date_value),
            "channel": "amazon",
            "profile_id": profile_id,
            "country_code": resolved_country if resolved_country != "UNKNOWN" else None,
            "marketplace": resolved_marketplace if resolved_marketplace != "unknown" else None,
            "currency": resolved_currency or currency or SalesTrafficIngestionService._currency_from_sales(sales),
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
    def _canonical_market_key(country_code: str | None, marketplace: str | None, currency: str | None) -> tuple[str, str, str]:
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
    def _is_unknown_aggregate(normalized: dict[str, Any]) -> bool:
        return not normalized.get("country_code") and not normalized.get("marketplace")

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
