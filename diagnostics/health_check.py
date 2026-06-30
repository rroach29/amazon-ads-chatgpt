"""
Business OS v8.1 — Diagnostics

A safe, Swagger-first platform diagnostics service. This endpoint is designed
as a pre-flight check before deeper Swagger testing. It should never raise for
normal subsystem failures; each check reports OK/WARN/ERROR independently.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import text

from database import SessionLocal


PLATFORM_VERSION = "8.1.0-diagnostics"


class BusinessOSDiagnostics:
    """Runs lightweight health checks across Business OS platform layers."""

    CRITICAL_TABLES = [
        "daily_dashboards",
        "campaign_daily_details",
        "search_term_daily_details",
        "decision_history",
        "scheduled_report_jobs",
    ]

    OPTIONAL_PLATFORM_TABLES = [
        "decision_outcomes",
        "learning_events",
        "confidence_history",
        "optimizer_metrics",
        "business_graph_nodes",
        "business_graph_edges",
        "schema_migrations",
    ]

    AMAZON_ENV_VARS = [
        "AMAZON_CLIENT_ID",
        "AMAZON_CLIENT_SECRET",
        "AMAZON_REFRESH_TOKEN",
        "AMAZON_PROFILE_ID",
    ]

    @classmethod
    def run(cls, country_code: str | None = None, profile_id: str | None = None) -> dict[str, Any]:
        checks = {
            "database": cls._safe("database", cls._check_database),
            "schema": cls._safe("schema", cls._check_schema),
            "migrations": cls._safe("migrations", cls._check_migrations),
            "dashboard": cls._safe("dashboard", lambda: cls._check_dashboard(country_code, profile_id)),
            "data_context": cls._safe("data_context", lambda: cls._check_data_context(country_code, profile_id)),
            "optimizer_registry": cls._safe("optimizer_registry", cls._check_optimizer_registry),
            "knowledge_graph": cls._safe("knowledge_graph", lambda: cls._check_knowledge_graph(country_code, profile_id)),
            "learning_engine": cls._safe("learning_engine", cls._check_learning_engine),
            "mission_control": cls._safe("mission_control", lambda: cls._check_mission_control(country_code, profile_id)),
            "executive_ai": cls._safe("executive_ai", lambda: cls._check_executive_ai(country_code, profile_id)),
            "amazon_ads_config": cls._safe("amazon_ads_config", cls._check_amazon_ads_config),
        }

        summary = cls._summarize(checks)
        return {
            "status": summary["status"],
            "platform_version": PLATFORM_VERSION,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "scope": {
                "country_code": country_code.upper() if isinstance(country_code, str) else country_code,
                "profile_id": profile_id,
            },
            "summary": summary,
            "checks": checks,
            "recommendation": cls._recommendation(summary, checks),
        }

    @staticmethod
    def _safe(name: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            result = fn()
            if not isinstance(result, dict):
                return {"status": "WARN", "message": f"{name} returned a non-dict result."}
            result.setdefault("status", "OK")
            return result
        except Exception as exc:  # diagnostics must not become the outage
            return {
                "status": "ERROR",
                "message": f"{name} check failed.",
                "error": str(exc),
            }

    @classmethod
    def _check_database(cls) -> dict[str, Any]:
        db = SessionLocal()
        try:
            value = db.execute(text("SELECT 1 AS ok")).scalar()
            return {"status": "OK" if value == 1 else "ERROR", "message": "Database connection verified."}
        finally:
            db.close()

    @classmethod
    def _check_schema(cls) -> dict[str, Any]:
        db = SessionLocal()
        try:
            rows = db.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public';
                    """
                )
            ).fetchall()
            tables = {row._mapping["table_name"] for row in rows}
            missing_critical = [table for table in cls.CRITICAL_TABLES if table not in tables]
            missing_optional = [table for table in cls.OPTIONAL_PLATFORM_TABLES if table not in tables]

            status = "OK" if not missing_critical else "ERROR"
            if not missing_critical and missing_optional:
                status = "WARN"

            return {
                "status": status,
                "table_count": len(tables),
                "missing_critical_tables": missing_critical,
                "missing_optional_tables": missing_optional,
                "message": "Schema check complete.",
            }
        finally:
            db.close()

    @classmethod
    def _check_migrations(cls) -> dict[str, Any]:
        db = SessionLocal()
        try:
            exists = db.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'schema_migrations'
                    ) AS exists;
                    """
                )
            ).scalar()
            if not exists:
                return {
                    "status": "WARN",
                    "message": "schema_migrations table not found. Run admin migrations if needed.",
                    "migrations": [],
                }

            rows = db.execute(
                text(
                    """
                    SELECT version, name, status, applied_at
                    FROM schema_migrations
                    ORDER BY applied_at DESC, id DESC
                    LIMIT 10;
                    """
                )
            ).fetchall()
            migrations = []
            for row in rows:
                item = dict(row._mapping)
                if item.get("applied_at") is not None:
                    item["applied_at"] = item["applied_at"].isoformat()
                migrations.append(item)
            return {
                "status": "OK",
                "count": len(migrations),
                "latest": migrations[0] if migrations else None,
                "migrations": migrations,
            }
        finally:
            db.close()

    @staticmethod
    def _check_dashboard(country_code: str | None, profile_id: str | None) -> dict[str, Any]:
        from dashboard import get_latest_dashboard

        dashboard = get_latest_dashboard(country_code=country_code, profile_id=profile_id)
        if not dashboard or dashboard.get("status") in {"ERROR", "NOT_FOUND"}:
            return {"status": "WARN", "message": "No latest dashboard found.", "dashboard": dashboard}
        return {
            "status": "OK",
            "date": dashboard.get("date"),
            "spend": dashboard.get("spend"),
            "sales": dashboard.get("sales"),
            "acos": dashboard.get("acos"),
            "roas": dashboard.get("roas"),
            "country_code": dashboard.get("country_code"),
            "profile_id": dashboard.get("profile_id"),
        }

    @staticmethod
    def _check_data_context(country_code: str | None, profile_id: str | None) -> dict[str, Any]:
        from business_data_context import resolve_data_context

        context = resolve_data_context(window="latest", country_code=country_code, profile_id=profile_id)
        status = context.get("status", "OK") if isinstance(context, dict) else "WARN"
        return {"status": status, "context": context}

    @staticmethod
    def _check_optimizer_registry() -> dict[str, Any]:
        from optimizers.optimizer_registry import list_optimizers

        result = list_optimizers()
        optimizers = result.get("optimizers", []) if isinstance(result, dict) else []
        return {
            "status": "OK" if optimizers else "WARN",
            "count": len(optimizers),
            "optimizers": optimizers,
        }

    @staticmethod
    def _check_knowledge_graph(country_code: str | None, profile_id: str | None) -> dict[str, Any]:
        from knowledge_graph import RelationshipService

        graph = RelationshipService.build_graph(country_code=country_code, profile_id=profile_id, limit=25)
        nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
        edges = graph.get("edges", []) if isinstance(graph, dict) else []
        return {
            "status": graph.get("status", "OK") if isinstance(graph, dict) else "WARN",
            "node_count": len(nodes),
            "edge_count": len(edges),
            "message": "Knowledge Graph built successfully.",
        }

    @staticmethod
    def _check_learning_engine() -> dict[str, Any]:
        db = SessionLocal()
        try:
            tables = ["decision_outcomes", "learning_events", "confidence_history", "optimizer_metrics"]
            counts: dict[str, int | None] = {}
            missing = []
            for table in tables:
                exists = db.execute(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.tables
                            WHERE table_schema = 'public' AND table_name = :table
                        ) AS exists;
                        """
                    ),
                    {"table": table},
                ).scalar()
                if not exists:
                    missing.append(table)
                    counts[table] = None
                    continue
                counts[table] = int(db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)
            return {
                "status": "OK" if not missing else "WARN",
                "missing_tables": missing,
                "counts": counts,
            }
        finally:
            db.close()

    @staticmethod
    def _check_mission_control(country_code: str | None, profile_id: str | None) -> dict[str, Any]:
        from mission_control import get_mission_control

        result = get_mission_control(country_code=country_code, profile_id=profile_id)
        if not isinstance(result, dict):
            return {"status": "WARN", "message": "Mission Control returned unexpected response."}
        return {
            "status": result.get("status", "OK"),
            "has_marketplace_summary": bool(result.get("marketplace_summary")),
            "has_business_plans": bool(result.get("business_plans")),
            "decision_count": result.get("decision_count") or result.get("open_decision_count"),
        }

    @staticmethod
    def _check_executive_ai(country_code: str | None, profile_id: str | None) -> dict[str, Any]:
        from executive import ExecutiveBriefingService

        result = ExecutiveBriefingService.what_should_i_do_today(
            objective=None,
            window="latest",
            country_code=country_code,
            profile_id=profile_id,
        )
        if not isinstance(result, dict):
            return {"status": "WARN", "message": "Executive AI returned unexpected response."}
        priorities = result.get("priorities", []) or result.get("items", []) or []
        return {
            "status": result.get("status", "OK"),
            "priority_count": len(priorities) if isinstance(priorities, list) else None,
            "message": result.get("narrative") or result.get("message") or "Executive AI check complete.",
        }

    @classmethod
    def _check_amazon_ads_config(cls) -> dict[str, Any]:
        configured = {name: bool(os.getenv(name)) for name in cls.AMAZON_ENV_VARS}
        missing = [name for name, ok in configured.items() if not ok]
        return {
            "status": "OK" if not missing else "WARN",
            "configured": configured,
            "missing": missing,
            "message": "Amazon Ads environment variables are configured." if not missing else "Some Amazon Ads environment variables are missing.",
        }

    @staticmethod
    def _summarize(checks: dict[str, dict[str, Any]]) -> dict[str, Any]:
        statuses = {name: check.get("status", "UNKNOWN") for name, check in checks.items()}
        error_count = sum(1 for status in statuses.values() if status == "ERROR")
        warn_count = sum(1 for status in statuses.values() if status == "WARN")
        ok_count = sum(1 for status in statuses.values() if status == "OK")
        overall = "OK"
        if error_count:
            overall = "ERROR"
        elif warn_count:
            overall = "WARN"
        return {
            "status": overall,
            "ok": ok_count,
            "warnings": warn_count,
            "errors": error_count,
            "total_checks": len(checks),
            "statuses": statuses,
        }

    @staticmethod
    def _recommendation(summary: dict[str, Any], checks: dict[str, dict[str, Any]]) -> str:
        if summary.get("errors"):
            failing = [name for name, check in checks.items() if check.get("status") == "ERROR"]
            return f"Fix failing diagnostics before continuing Swagger regression tests: {', '.join(failing)}."
        if summary.get("warnings"):
            warnings = [name for name, check in checks.items() if check.get("status") == "WARN"]
            return f"Platform is usable, but review warnings before major releases: {', '.join(warnings)}."
        return "System healthy. Proceed with Swagger regression testing."
