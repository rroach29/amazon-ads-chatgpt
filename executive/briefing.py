"""
Business OS v8.0 — Executive Briefing Service

Builds the daily AI COO layer: what changed, what matters, what to do next, and
how confident the system is.
"""

from __future__ import annotations

from typing import Any

from mission_control import get_mission_control, get_marketplace_summary_for_mission_control

try:
    from knowledge_graph import ProductIntelligenceService
except Exception:  # pragma: no cover - defensive for partial deployments
    ProductIntelligenceService = None

try:
    from outcome_intelligence import DecisionAnalytics, OptimizerScorecard
except Exception:  # pragma: no cover
    DecisionAnalytics = None
    OptimizerScorecard = None

try:
    from learning.summary import build_learning_intelligence
except Exception:  # pragma: no cover
    build_learning_intelligence = None

from .objectives import BusinessObjectives
from .priority_engine import ExecutivePriorityEngine


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except Exception:
        return default


class ExecutiveBriefingService:
    @staticmethod
    def briefing(
        objective: str | None = None,
        window: str = "latest",
        country_code: str | None = None,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        objective_config = BusinessObjectives.get(objective)
        mission = get_mission_control(
            objective=objective_config.get("label"),
            window=window,
            country_code=country_code,
            profile_id=profile_id,
        )
        priorities = ExecutivePriorityEngine.build_priorities(
            objective=objective_config.get("key"),
            window=window,
            country_code=country_code,
            profile_id=profile_id,
            max_priorities=7,
        )
        marketplace_summary = get_marketplace_summary_for_mission_control(country_code=country_code, profile_id=profile_id)
        product_summary = ExecutiveBriefingService._safe_product_summary(country_code, profile_id)
        analytics = ExecutiveBriefingService._safe_analytics()
        scorecard = ExecutiveBriefingService._safe_scorecard()
        learning = ExecutiveBriefingService._safe_learning()

        executive_summary = ExecutiveBriefingService._executive_summary(
            objective_config=objective_config,
            mission=mission,
            priorities=priorities,
            marketplace_summary=marketplace_summary,
            product_summary=product_summary,
            analytics=analytics,
            learning=learning,
        )

        return {
            "status": "OK",
            "version": "8.0",
            "title": "Mission Control 2.0 — Executive AI",
            "objective": objective_config,
            "executive_summary": executive_summary,
            "what_should_i_do_today": priorities.get("priorities", [])[:5],
            "strategic_signals": priorities.get("strategic_signals", []),
            "marketplace_summary": marketplace_summary,
            "product_intelligence": product_summary,
            "current_plan": mission.get("current_plan"),
            "simulation": mission.get("simulation"),
            "decision_analytics": analytics,
            "optimizer_scorecard": scorecard,
            "learning": learning,
            "operating_mode": {
                "role": "AI_COO_EXECUTIVE_LAYER",
                "approval_required": True,
                "uses_existing_decision_workflow": True,
                "live_execution_requires_existing_safety_checks": True,
            },
            "next_operating_questions": [
                "Which executive priorities should be approved today?",
                "Which marketplace is improving or deteriorating?",
                "Which optimizer is creating the most reliable value?",
                "Which product family deserves budget or efficiency attention?",
            ],
        }

    @staticmethod
    def what_should_i_do_today(
        objective: str | None = None,
        window: str = "latest",
        country_code: str | None = None,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        priorities = ExecutivePriorityEngine.build_priorities(
            objective=objective,
            window=window,
            country_code=country_code,
            profile_id=profile_id,
            max_priorities=5,
        )
        return {
            "status": priorities.get("status"),
            "version": "8.0",
            "objective": priorities.get("objective"),
            "count": priorities.get("priority_count"),
            "items": priorities.get("priorities", []),
            "strategic_signals": priorities.get("strategic_signals", []),
            "narrative": priorities.get("narrative"),
        }

    @staticmethod
    def _safe_product_summary(country_code: str | None, profile_id: str | None) -> dict[str, Any]:
        if not ProductIntelligenceService:
            return {"status": "UNAVAILABLE", "message": "Product intelligence service is not available."}
        try:
            return ProductIntelligenceService.product_summary(country_code=country_code, profile_id=profile_id)
        except Exception as exc:
            return {"status": "ERROR", "message": str(exc)}

    @staticmethod
    def _safe_analytics() -> dict[str, Any]:
        if not DecisionAnalytics:
            return {"status": "UNAVAILABLE"}
        try:
            return DecisionAnalytics.analytics()
        except Exception as exc:
            return {"status": "ERROR", "message": str(exc)}

    @staticmethod
    def _safe_scorecard() -> dict[str, Any]:
        if not OptimizerScorecard:
            return {"status": "UNAVAILABLE"}
        try:
            return OptimizerScorecard.scorecard()
        except Exception as exc:
            return {"status": "ERROR", "message": str(exc)}

    @staticmethod
    def _safe_learning() -> dict[str, Any]:
        if not build_learning_intelligence:
            return {"status": "UNAVAILABLE"}
        try:
            return build_learning_intelligence()
        except Exception as exc:
            return {"status": "ERROR", "message": str(exc)}

    @staticmethod
    def _executive_summary(
        objective_config: dict[str, Any],
        mission: dict[str, Any],
        priorities: dict[str, Any],
        marketplace_summary: dict[str, Any],
        product_summary: dict[str, Any],
        analytics: dict[str, Any],
        learning: dict[str, Any],
    ) -> dict[str, Any]:
        priority_items = priorities.get("priorities", []) or []
        top = priority_items[0] if priority_items else None
        combined = marketplace_summary.get("combined") if isinstance(marketplace_summary, dict) else {}
        analytics_summary = analytics.get("summary") if isinstance(analytics, dict) else {}

        headline_parts = [f"Operating objective is {objective_config.get('label')}"]
        if isinstance(combined, dict) and combined:
            headline_parts.append(
                f"combined spend is {combined.get('spend')} and sales are {combined.get('sales')}"
            )
        if top:
            headline_parts.append(f"top priority is {top.get('decision')}")

        return {
            "headline": "; ".join(headline_parts) + ".",
            "top_priority": top,
            "priority_count": len(priority_items),
            "expected_monthly_impact": mission.get("current_plan", {}).get("expected_monthly_impact"),
            "plan_confidence": mission.get("current_plan", {}).get("confidence"),
            "plan_risk": mission.get("current_plan", {}).get("risk"),
            "marketplace_health": {
                "combined_acos": combined.get("acos") if isinstance(combined, dict) else None,
                "combined_roas": combined.get("roas") if isinstance(combined, dict) else None,
                "average_health_score": combined.get("average_health_score") if isinstance(combined, dict) else None,
            },
            "product_count": product_summary.get("product_count") if isinstance(product_summary, dict) else None,
            "decision_system": {
                "total_decisions": analytics_summary.get("total_decisions") if isinstance(analytics_summary, dict) else None,
                "evaluated_decisions": analytics_summary.get("evaluated_decisions") if isinstance(analytics_summary, dict) else None,
                "success_rate": analytics_summary.get("success_rate") if isinstance(analytics_summary, dict) else None,
            },
            "learning_status": learning.get("narrative") if isinstance(learning, dict) else None,
            "executive_interpretation": ExecutiveBriefingService._interpretation(top, combined),
        }

    @staticmethod
    def _interpretation(top: dict[str, Any] | None, combined: dict[str, Any] | None) -> str:
        if not top:
            return "No urgent action is currently available; monitor the business and wait for higher-confidence signals."
        acos = _safe_float((combined or {}).get("acos"), default=0)
        if acos > 100 and top.get("decision") in {"ADD_NEGATIVE_KEYWORD", "REDUCE_BID", "DECREASE_BUDGET"}:
            return "Efficiency pressure is high, and the top recommendation directly addresses wasted spend or margin protection."
        if top.get("decision") in {"INCREASE_BID", "INCREASE_BUDGET"}:
            return "The top recommendation is a controlled scaling action; review profitability and approve only if the payload matches your current growth appetite."
        return "The top recommendation is ready for review through the standard approval workflow."
