"""Business OS v0.4.2 — Mission Control v2.

Purpose:
- Surface intelligence-engine decisions ahead of setup/registry noise.
- Rank decisions using business impact + confidence + urgency.
- Support source/category filtering.
- Add a clean executive queue endpoint for the frontend/GPT.
- Keep old v0.3 Mission Control intact for rollback safety.

This service reads the existing mission_control_decisions table created in v0.3.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import desc

from database import SessionLocal
from business_os.mission_control.models import MissionControlDecision


class MissionControlV2Service:
    version = "business-os-0.4.2"

    BUSINESS_SOURCES = {
        "product_search_intelligence",
        "product_advertising_intelligence",
        "mission_control_engine",
    }

    LOW_SIGNAL_CATEGORIES = {
        "Registry",
        "Setup",
        "Data Quality",
    }

    SOURCE_WEIGHT = {
        "product_search_intelligence": 1.35,
        "product_advertising_intelligence": 1.30,
        "mission_control_engine": 1.00,
    }

    CATEGORY_WEIGHT = {
        "Search Terms": 1.35,
        "Advertising": 1.25,
        "Profit": 1.20,
        "Growth": 1.15,
        "Registry": 0.45,
        "Setup": 0.40,
        "Data Quality": 0.55,
    }

    @classmethod
    def executive_queue(
        cls,
        status: str = "Pending",
        limit: int = 100,
        include_setup: bool = False,
        source: str | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        db = SessionLocal()
        try:
            rows = cls._query_rows(
                db=db,
                status=status,
                limit=max(limit * 3, 100),
                source=source,
                category=category,
            )

            ranked = []
            for row in rows:
                item = cls._decision(row)
                item["executive_priority"] = cls._executive_priority(row)
                item["decision_type"] = cls._decision_type(row)
                item["is_setup"] = cls._is_setup(row)
                ranked.append(item)

            if not include_setup:
                ranked = [item for item in ranked if not item["is_setup"]]

            ranked.sort(key=lambda item: item["executive_priority"], reverse=True)
            ranked = ranked[: max(1, min(limit, 500))]

            top_three = ranked[:3]
            next_ten = ranked[3:13]
            setup_backlog = []
            if not include_setup:
                setup_backlog = [
                    cls._decision(row) | {
                        "executive_priority": cls._executive_priority(row),
                        "decision_type": cls._decision_type(row),
                        "is_setup": True,
                    }
                    for row in rows
                    if cls._is_setup(row)
                ][:25]

            return {
                "status": "OK",
                "version": cls.version,
                "count": len(ranked),
                "include_setup": include_setup,
                "filters": {
                    "status": status,
                    "source": source,
                    "category": category,
                },
                "summary": cls._summary(ranked, setup_backlog),
                "top_three": top_three,
                "next_ten": next_ten,
                "decisions": ranked,
                "setup_backlog": setup_backlog,
            }
        finally:
            db.close()

    @classmethod
    def summary(cls) -> dict[str, Any]:
        db = SessionLocal()
        try:
            pending = (
                db.query(MissionControlDecision)
                .filter(MissionControlDecision.status == "Pending")
                .all()
            )

            business_rows = [row for row in pending if not cls._is_setup(row)]
            setup_rows = [row for row in pending if cls._is_setup(row)]
            ranked = sorted(
                business_rows,
                key=lambda row: cls._executive_priority(row),
                reverse=True,
            )

            sources = defaultdict(int)
            categories = defaultdict(int)
            for row in pending:
                sources[row.source or "unknown"] += 1
                categories[row.category or "unknown"] += 1

            top_three = ranked[:3]
            opportunity = sum(float(row.estimated_monthly_impact or 0) for row in top_three)

            return {
                "status": "OK",
                "version": cls.version,
                "pending_total": len(pending),
                "pending_business_decisions": len(business_rows),
                "pending_setup_decisions": len(setup_rows),
                "top_three_estimated_monthly_impact": round(opportunity, 2),
                "sources": dict(sorted(sources.items())),
                "categories": dict(sorted(categories.items())),
                "top_three": [
                    cls._decision(row) | {
                        "executive_priority": cls._executive_priority(row),
                        "decision_type": cls._decision_type(row),
                        "is_setup": False,
                    }
                    for row in top_three
                ],
            }
        finally:
            db.close()

    @classmethod
    def cleanup_setup_noise(cls, dry_run: bool = True) -> dict[str, Any]:
        """Dismiss low-signal setup rows that are drowning out business decisions.

        This does NOT delete rows. It changes Pending registry/setup decisions to
        Dismissed only when dry_run=False.
        """
        db = SessionLocal()
        try:
            rows = (
                db.query(MissionControlDecision)
                .filter(MissionControlDecision.status == "Pending")
                .all()
            )
            setup_rows = [row for row in rows if cls._is_setup(row)]

            if not dry_run:
                now = datetime.utcnow()
                for row in setup_rows:
                    row.status = "Dismissed"
                    row.dismissed_at = now
                    row.updated_at = now
                db.commit()

            return {
                "status": "OK",
                "version": cls.version,
                "dry_run": dry_run,
                "setup_decisions_matched": len(setup_rows),
                "message": (
                    "Dry run only. No rows changed."
                    if dry_run
                    else f"Dismissed {len(setup_rows)} setup/registry decisions."
                ),
            }
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @classmethod
    def search_decisions(cls, limit: int = 100) -> dict[str, Any]:
        return cls.executive_queue(
            status="Pending",
            limit=limit,
            include_setup=False,
            source="product_search_intelligence",
        )

    @classmethod
    def advertising_decisions(cls, limit: int = 100) -> dict[str, Any]:
        return cls.executive_queue(
            status="Pending",
            limit=limit,
            include_setup=False,
            source="product_advertising_intelligence",
        )

    @classmethod
    def _query_rows(
        cls,
        db,
        status: str,
        limit: int,
        source: str | None = None,
        category: str | None = None,
    ) -> list[MissionControlDecision]:
        query = db.query(MissionControlDecision)
        if status:
            query = query.filter(MissionControlDecision.status == status)
        if source:
            query = query.filter(MissionControlDecision.source == source)
        if category:
            query = query.filter(MissionControlDecision.category == category)

        return (
            query.order_by(
                desc(MissionControlDecision.urgency),
                desc(MissionControlDecision.estimated_monthly_impact),
                desc(MissionControlDecision.created_at),
            )
            .limit(max(1, min(limit, 1000)))
            .all()
        )

    @classmethod
    def _executive_priority(cls, row: MissionControlDecision) -> int:
        impact = float(row.estimated_monthly_impact or 0)
        confidence = int(row.confidence or 0)
        urgency = int(row.urgency or 0)

        # Normalize impact so small setup estimates do not dominate.
        impact_score = min(100, impact / 3)

        source_weight = cls.SOURCE_WEIGHT.get(row.source or "", 0.90)
        category_weight = cls.CATEGORY_WEIGHT.get(row.category or "", 1.00)

        if cls._is_setup(row):
            category_weight = min(category_weight, 0.45)

        score = (
            impact_score * 0.42
            + confidence * 0.28
            + urgency * 0.30
        ) * source_weight * category_weight

        return max(0, min(100, round(score)))

    @classmethod
    def _is_setup(cls, row: MissionControlDecision) -> bool:
        category = row.category or ""
        title = (row.title or "").lower()
        recommendation = (row.recommendation or "").lower()

        if category in cls.LOW_SIGNAL_CATEGORIES:
            return True

        if "complete channel mappings" in title:
            return True

        if "missing amazon/shopify/etsy identifiers" in recommendation:
            return True

        if row.source == "mission_control_engine" and category in {"Registry", "Setup"}:
            return True

        return False

    @classmethod
    def _decision_type(cls, row: MissionControlDecision) -> str:
        if cls._is_setup(row):
            return "Setup"
        if row.source == "product_search_intelligence":
            return "Search Intelligence"
        if row.source == "product_advertising_intelligence":
            return "Advertising Intelligence"
        if row.category:
            return row.category
        return "Business Decision"

    @classmethod
    def _summary(cls, ranked: list[dict[str, Any]], setup_backlog: list[dict[str, Any]]) -> dict[str, Any]:
        top_three = ranked[:3]
        opportunity = sum(float(item.get("estimated_monthly_impact") or 0) for item in top_three)

        by_type = defaultdict(int)
        by_source = defaultdict(int)
        by_category = defaultdict(int)

        for item in ranked:
            by_type[item.get("decision_type") or "Unknown"] += 1
            by_source[item.get("source") or "unknown"] += 1
            by_category[item.get("category") or "unknown"] += 1

        return {
            "business_decisions": len(ranked),
            "setup_backlog": len(setup_backlog),
            "top_three_estimated_monthly_impact": round(opportunity, 2),
            "by_type": dict(sorted(by_type.items())),
            "by_source": dict(sorted(by_source.items())),
            "by_category": dict(sorted(by_category.items())),
        }

    @staticmethod
    def _decision(row: MissionControlDecision) -> dict[str, Any]:
        return {
            "id": row.id,
            "decision_id": row.decision_id,
            "master_product_id": row.master_product_id,
            "product_name": row.product_name,
            "title": row.title,
            "category": row.category,
            "priority": row.priority,
            "status": row.status,
            "estimated_monthly_impact": row.estimated_monthly_impact,
            "confidence": row.confidence,
            "reversibility": row.reversibility,
            "urgency": row.urgency,
            "recommendation": row.recommendation,
            "reason": row.reason,
            "why_now": row.why_now,
            "if_you_do": row.if_you_do,
            "if_you_do_not": row.if_you_do_not,
            "evidence": row.evidence,
            "actions": row.actions,
            "source": row.source,
            "approved": row.approved,
            "approved_at": row.approved_at.isoformat() if row.approved_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
