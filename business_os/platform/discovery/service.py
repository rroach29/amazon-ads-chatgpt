"""Executive Brain v2.1 — Database Discovery Engine.

Purpose:
Inspect the live database so future linking/scoring engines use the actual schema,
not guessed column names.

This engine is read-only.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import inspect, text

from database import SessionLocal, engine


class DatabaseDiscoveryService:
    version = "executive-brain-2.1"

    KEYWORD_GROUPS = {
        "product_identifiers": ["sku", "asin", "fnsku", "msku", "product_id", "listing_id", "item_id"],
        "marketplace": ["marketplace", "country_code", "currency", "profile_id", "channel"],
        "sales": ["sales", "revenue", "orders", "units", "sessions", "page_views"],
        "ads": ["spend", "clicks", "impressions", "acos", "roas", "campaign", "ad_group", "keyword", "search_term"],
        "registry": ["master_product_id", "brand", "product_family", "primary_sku"],
        "dates": ["date", "created_at", "updated_at", "requested_at", "completed_at"],
    }

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
            total_rows = cls._safe_scalar(db, f"SELECT COUNT(*) FROM {table_name}") or 0

            column_profiles = []
            for column in column_names:
                non_null = cls._safe_scalar(db, f"SELECT COUNT(*) FROM {table_name} WHERE {column} IS NOT NULL")
                distinct_count = cls._safe_scalar(db, f"SELECT COUNT(DISTINCT {column}) FROM {table_name} WHERE {column} IS NOT NULL")
                samples = cls._safe_samples(db, table_name, column, limit=3)
                column_profiles.append(
                    {
                        "name": column,
                        "type": str(next((c.get("type") for c in columns if c["name"] == column), "")),
                        "non_null_count": non_null,
                        "non_null_pct": round(non_null / total_rows, 4) if total_rows else None,
                        "distinct_count": distinct_count,
                        "sample_values": samples,
                        "semantic_groups": cls._semantic_groups(column),
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
        """Read-only diagnostics for why Product Genomes may show zero rows."""
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
                    linked_rows = cls._safe_scalar(db, f"SELECT COUNT(*) FROM {table} WHERE master_product_id IS NOT NULL") or 0

                identifier_columns = []
                for col in profile["columns"]:
                    if "product_identifiers" in col.get("semantic_groups", []) or col["name"] in {"sku", "asin"}:
                        identifier_columns.append({
                            "name": col["name"],
                            "non_null_count": col["non_null_count"],
                            "sample_values": col["sample_values"],
                        })

                result["tables"][table] = {
                    "row_count": profile["row_count"],
                    "has_master_product_id": has_mpid,
                    "linked_rows": linked_rows,
                    "identifier_columns": identifier_columns,
                    "sample_rows": profile["sample_rows"],
                    "diagnosis": cls._diagnosis(profile, has_mpid, linked_rows, identifier_columns),
                }

            result["registry"] = {
                "master_products": cls._safe_scalar(db, "SELECT COUNT(*) FROM master_products") if cls._table_exists("master_products") else None,
                "product_channels": cls._safe_scalar(db, "SELECT COUNT(*) FROM product_channels") if cls._table_exists("product_channels") else None,
                "mapped_channels": cls._safe_scalar(db, "SELECT COUNT(*) FROM product_channels WHERE status = 'Mapped'") if cls._table_exists("product_channels") else None,
            }
            return result
        finally:
            db.close()

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
        populated = [c for c in identifier_columns if c["non_null_count"]]
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
                text(f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL LIMIT :limit"),
                {"limit": limit},
            ).fetchall()
            return [str(row[0])[:200] for row in rows]
        except Exception:
            return []

    @classmethod
    def _safe_rows(cls, db, table: str, limit: int = 5) -> list[dict[str, Any]]:
        try:
            rows = db.execute(text(f"SELECT * FROM {table} LIMIT :limit"), {"limit": limit}).mappings().all()
            return [{k: cls._json_safe(v) for k, v in dict(row).items()} for row in rows]
        except Exception as exc:
            return [{"error": str(exc)}]

    @staticmethod
    def _json_safe(value):
        if hasattr(value, "isoformat"):
            return value.isoformat()
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
                "non_null_count": c["non_null_count"],
                "non_null_pct": c["non_null_pct"],
                "sample_values": c["sample_values"],
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
