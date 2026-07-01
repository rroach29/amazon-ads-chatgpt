"""Executive Brain v2.1.2 — Database Discovery Engine hotfix.

Fixes:
- non_null count may return None, causing division errors.
- keeps discovery read-only and defensive.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import inspect, text

from database import SessionLocal, engine


class DatabaseDiscoveryService:
    version = "executive-brain-2.1.2"

    KEYWORD_GROUPS = {
        "product_identifiers": ["sku", "asin", "fnsku", "msku", "product_id", "listing_id", "item_id"],
        "marketplace": ["marketplace", "country_code", "currency", "profile_id", "channel"],
        "sales": ["sales", "revenue", "orders", "units", "sessions", "page_views"],
        "ads": ["spend", "clicks", "impressions", "acos", "roas", "campaign", "ad_group", "keyword", "search_term"],
        "registry": ["master_product_id", "brand", "product_family", "primary_sku"],
        "dates": ["date", "created_at", "updated_at", "requested_at", "completed_at"],
    }

    UNSAFE_DISTINCT_TYPES = ["JSON", "JSONB", "ARRAY", "BYTEA"]

    @classmethod
    def overview(cls) -> dict[str, Any]:
        inspector = inspect(engine)
        tables = sorted(inspector.get_table_names())
        return {
            "status": "OK",
            "version": cls.version,
            "table_count": len(tables),
            "tables": tables,
            "focus_tables": cls._focus_tables(tables),
            "note": "Discovery is read-only.",
        }

    @classmethod
    def table_profile(cls, table_name: str, sample_limit: int = 5) -> dict[str, Any]:
        inspector = inspect(engine)
        if not inspector.has_table(table_name):
            return {"status": "NOT_FOUND", "version": cls.version, "table": table_name}

        db = SessionLocal()
        try:
            columns = inspector.get_columns(table_name)
            column_names = [c["name"] for c in columns]
            total_rows = cls._to_int(cls._safe_scalar(db, f'SELECT COUNT(*) FROM "{table_name}"'), default=0)

            column_profiles = []
            for column in columns:
                column_name = column["name"]
                column_type = str(column.get("type", ""))
                quoted_column = cls._quote(column_name)

                raw_non_null = cls._safe_scalar(db, f'SELECT COUNT(*) FROM "{table_name}" WHERE {quoted_column} IS NOT NULL')
                non_null = cls._to_int(raw_non_null, default=0)

                distinct_count = None
                distinct_note = None

                if not cls._is_unsafe_distinct_type(column_type):
                    try:
                        raw_distinct = db.execute(
                            text(f'SELECT COUNT(DISTINCT {quoted_column}) FROM "{table_name}" WHERE {quoted_column} IS NOT NULL')
                        ).scalar()
                        distinct_count = cls._to_int(raw_distinct, default=0)
                    except Exception as exc:
                        distinct_note = str(exc)[:200]
                else:
                    distinct_note = f"Skipped DISTINCT for {column_type}"

                samples = cls._safe_samples(db, table_name, column_name, limit=3)
                column_profiles.append(
                    {
                        "name": column_name,
                        "type": column_type,
                        "non_null_count": non_null,
                        "non_null_pct": round(non_null / total_rows, 4) if total_rows > 0 else None,
                        "distinct_count": distinct_count,
                        "distinct_note": distinct_note,
                        "sample_values": samples,
                        "semantic_groups": cls._semantic_groups(column_name),
                    }
                )

            sample_rows = cls._safe_rows(db, table_name, limit=sample_limit)

            return {
                "status": "OK",
                "version": cls.version,
                "table": table_name,
                "row_count": total_rows,
                "column_count": len(column_names),
                "columns": column_profiles,
                "sample_rows": sample_rows,
                "likely_identifier_columns": cls._likely_columns(column_profiles, "product_identifiers"),
                "likely_registry_columns": cls._likely_columns(column_profiles, "registry"),
                "likely_sales_columns": cls._likely_columns(column_profiles, "sales"),
                "likely_ads_columns": cls._likely_columns(column_profiles, "ads"),
            }
        except Exception as exc:
            return {
                "status": "ERROR",
                "version": cls.version,
                "table": table_name,
                "message": str(exc),
                "hint": "Discovery returned an error object instead of raising Internal Server Error.",
            }
        finally:
            db.close()

    @classmethod
    def focus_profile(cls) -> dict[str, Any]:
        inspector = inspect(engine)
        tables = cls._focus_tables(inspector.get_table_names())
        profiles = {}
        for table in tables:
            profiles[table] = cls.table_profile(table_name=table, sample_limit=3)
        return {
            "status": "OK",
            "version": cls.version,
            "focus_table_count": len(tables),
            "profiles": profiles,
            "relationship_hypotheses": cls.relationship_hypotheses(),
            "amazon_scope": cls.amazon_scope(),
        }

    @classmethod
    def relationship_hypotheses(cls) -> dict[str, Any]:
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        hypotheses = []
        for table in tables:
            if not inspector.has_table(table):
                continue
            columns = [c["name"] for c in inspector.get_columns(table)]
            lower = {c.lower(): c for c in columns}

            if "master_product_id" in lower:
                hypotheses.append({
                    "table": table,
                    "relationship": "direct_master_product_link",
                    "column": lower["master_product_id"],
                    "confidence": "high",
                    "meaning": f"{table} can directly link to master_products.master_product_id.",
                })

            for candidate in ["sku", "asin", "advertisedsku", "advertisedasin", "purchasedsku", "purchasedasin"]:
                if candidate in lower:
                    hypotheses.append({
                        "table": table,
                        "relationship": "product_identifier_candidate",
                        "column": lower[candidate],
                        "confidence": "medium",
                        "meaning": f"{table}.{lower[candidate]} may resolve through master_products/product_channels.",
                    })

        return {
            "status": "OK",
            "version": cls.version,
            "hypotheses": hypotheses,
        }

    @classmethod
    def linking_diagnostics(cls) -> dict[str, Any]:
        db = SessionLocal()
        try:
            tables = ["seller_central_sales_traffic", "campaign_daily_details", "search_term_daily_details"]
            result = {"status": "OK", "version": cls.version, "tables": {}}

            for table in tables:
                profile = cls.table_profile(table, sample_limit=3)
                if profile.get("status") != "OK":
                    result["tables"][table] = profile
                    continue

                has_mpid = any(c["name"] == "master_product_id" for c in profile["columns"])
                linked_rows = None
                if has_mpid:
                    linked_rows = cls._to_int(
                        cls._safe_scalar(db, f'SELECT COUNT(*) FROM "{table}" WHERE master_product_id IS NOT NULL'),
                        default=0,
                    )

                identifier_columns = []
                for col in profile["columns"]:
                    if "product_identifiers" in col.get("semantic_groups", []) or col["name"] in {"sku", "asin"}:
                        identifier_columns.append({
                            "name": col["name"],
                            "non_null_count": cls._to_int(col.get("non_null_count"), default=0),
                            "sample_values": col.get("sample_values", []),
                        })

                result["tables"][table] = {
                    "row_count": profile["row_count"],
                    "has_master_product_id": has_mpid,
                    "linked_rows": linked_rows,
                    "identifier_columns": identifier_columns,
                    "sample_rows": profile["sample_rows"],
                    "diagnosis": cls._diagnosis(profile, has_mpid, linked_rows, identifier_columns),
                }

            result["registry"] = cls._registry_summary(db)
            result["amazon_scope"] = cls.amazon_scope()
            result["important_note"] = "Not every Master Product is expected to have Amazon data. Amazon-based Product Genomes should only score products with Amazon mappings or Amazon-linked rows."
            return result
        finally:
            db.close()

    @classmethod
    def amazon_scope(cls) -> dict[str, Any]:
        db = SessionLocal()
        try:
            if not cls._table_exists("product_channels"):
                return {"status": "NOT_READY", "reason": "product_channels table not found"}

            total_master_products = cls._to_int(cls._safe_scalar(db, 'SELECT COUNT(*) FROM "master_products"'), default=0) if cls._table_exists("master_products") else 0
            amazon_channel_rows = cls._to_int(cls._safe_scalar(
                db,
                """
                SELECT COUNT(*)
                FROM product_channels
                WHERE LOWER(channel) LIKE '%amazon%' OR LOWER(marketplace) LIKE '%amazon%'
                """,
            ), default=0)
            mapped_amazon_rows = cls._to_int(cls._safe_scalar(
                db,
                """
                SELECT COUNT(*)
                FROM product_channels
                WHERE (LOWER(channel) LIKE '%amazon%' OR LOWER(marketplace) LIKE '%amazon%')
                AND (
                    asin IS NOT NULL
                    OR channel_product_id IS NOT NULL
                    OR channel_listing_id IS NOT NULL
                    OR status = 'Mapped'
                )
                """,
            ), default=0)
            distinct_amazon_products = cls._to_int(cls._safe_scalar(
                db,
                """
                SELECT COUNT(DISTINCT master_product_id)
                FROM product_channels
                WHERE (LOWER(channel) LIKE '%amazon%' OR LOWER(marketplace) LIKE '%amazon%')
                AND (
                    asin IS NOT NULL
                    OR channel_product_id IS NOT NULL
                    OR channel_listing_id IS NOT NULL
                    OR status = 'Mapped'
                )
                """,
            ), default=0)

            return {
                "status": "OK",
                "version": cls.version,
                "total_master_products": total_master_products,
                "amazon_channel_rows": amazon_channel_rows,
                "mapped_amazon_channel_rows": mapped_amazon_rows,
                "distinct_master_products_with_amazon_mapping": distinct_amazon_products,
                "diagnosis": cls._amazon_scope_diagnosis(total_master_products, distinct_amazon_products),
            }
        finally:
            db.close()

    @staticmethod
    def _amazon_scope_diagnosis(total: int, amazon_mapped: int) -> str:
        if total and amazon_mapped == 0:
            return "The Registry has products, but no products currently have mapped Amazon channel identifiers. Amazon-only scoring will show zero until Amazon mappings are filled or rows are linked by SKU/ASIN."
        if amazon_mapped < total:
            return "Only a subset of Master Products appear to be mapped to Amazon. This is expected if some products are Shopify/Etsy/future-channel only."
        return "All Master Products appear to have Amazon mappings."

    @classmethod
    def _registry_summary(cls, db) -> dict[str, Any]:
        return {
            "master_products": cls._to_int(cls._safe_scalar(db, 'SELECT COUNT(*) FROM "master_products"'), default=0) if cls._table_exists("master_products") else None,
            "product_channels": cls._to_int(cls._safe_scalar(db, 'SELECT COUNT(*) FROM "product_channels"'), default=0) if cls._table_exists("product_channels") else None,
            "mapped_channels": cls._to_int(cls._safe_scalar(db, "SELECT COUNT(*) FROM product_channels WHERE status = 'Mapped'"), default=0) if cls._table_exists("product_channels") else None,
        }

    @classmethod
    def _diagnosis(cls, profile: dict, has_mpid: bool, linked_rows: int | None, identifier_columns: list[dict]) -> str:
        if profile["row_count"] == 0:
            return "No source rows exist in this table yet."
        if not has_mpid:
            return "Table has source rows but no master_product_id column yet."
        if linked_rows and linked_rows > 0:
            return "Rows are linked to Master Products."
        if not identifier_columns:
            return "Rows are unlinked and no obvious SKU/ASIN identifier columns were found."
        populated = [c for c in identifier_columns if cls._to_int(c.get("non_null_count"), default=0) > 0]
        if not populated:
            return "Identifier columns exist but appear empty, so exact matching cannot work."
        return "Identifier columns exist and are populated; linking rules likely need to match the actual column names/values."

    @classmethod
    def _safe_scalar(cls, db, sql: str):
        try:
            return db.execute(text(sql)).scalar()
        except Exception:
            return None

    @classmethod
    def _safe_samples(cls, db, table: str, column: str, limit: int = 3) -> list[Any]:
        try:
            rows = db.execute(
                text(f'SELECT DISTINCT {cls._quote(column)}::TEXT FROM "{table}" WHERE {cls._quote(column)} IS NOT NULL LIMIT :limit'),
                {"limit": limit},
            ).fetchall()
            return [str(row[0])[:200] for row in rows]
        except Exception as exc:
            return [f"sample_error: {str(exc)[:120]}"]

    @classmethod
    def _safe_rows(cls, db, table: str, limit: int = 5) -> list[dict[str, Any]]:
        try:
            rows = db.execute(text(f'SELECT * FROM "{table}" LIMIT :limit'), {"limit": limit}).mappings().all()
            return [{k: cls._json_safe(v) for k, v in dict(row).items()} for row in rows]
        except Exception as exc:
            return [{"error": str(exc)}]

    @staticmethod
    def _json_safe(value):
        if hasattr(value, "isoformat"):
            return value.isoformat()
        if isinstance(value, (dict, list)):
            return value
        return value

    @classmethod
    def _semantic_groups(cls, column_name: str) -> list[str]:
        lower = column_name.lower()
        groups = []
        for group, keywords in cls.KEYWORD_GROUPS.items():
            if any(keyword in lower for keyword in keywords):
                groups.append(group)
        return groups

    @classmethod
    def _likely_columns(cls, column_profiles: list[dict], group: str) -> list[dict]:
        return [
            {
                "name": c["name"],
                "non_null_count": cls._to_int(c.get("non_null_count"), default=0),
                "non_null_pct": c.get("non_null_pct"),
                "sample_values": c.get("sample_values", []),
            }
            for c in column_profiles
            if group in c.get("semantic_groups", [])
        ]

    @staticmethod
    def _focus_tables(tables: list[str]) -> list[str]:
        wanted = [
            "master_products",
            "product_channels",
            "product_genomes",
            "seller_central_sales_traffic",
            "campaign_daily_details",
            "search_term_daily_details",
            "daily_dashboards",
            "optimization_queue",
            "decision_history",
        ]
        return [t for t in wanted if t in tables]

    @staticmethod
    def _table_exists(table: str) -> bool:
        inspector = inspect(engine)
        return inspector.has_table(table)

    @staticmethod
    def _quote(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    @classmethod
    def _is_unsafe_distinct_type(cls, column_type: str) -> bool:
        upper = str(column_type).upper()
        return any(token in upper for token in cls.UNSAFE_DISTINCT_TYPES)

    @staticmethod
    def _to_int(value: Any, default: int = 0) -> int:
        try:
            if value is None:
                return default
            return int(value)
        except Exception:
            return default
