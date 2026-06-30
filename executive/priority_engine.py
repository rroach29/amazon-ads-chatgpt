"""
Business OS v8.0 — Executive Prioritization Engine

Ranks work across optimizers and open decisions using objective-aware scoring.
This layer intentionally consumes existing Business OS services instead of adding
new tables or one-off data paths.
"""

from __future__ import annotations

from typing import Any

from business_plan_engine import build_business_plan, simulate_business_plan
from business_data_context import resolve_data_context
from mission_control import get_marketplace_summary_for_mission_control
from optimizers.optimizer_registry import run_all_optimizers

from .objectives import BusinessObjectives


RISK_PENALTY = {
    "LOW": 0,
    "MEDIUM": 12,
    "HIGH": 35,
}

GROWTH_DECISIONS = {"INCREASE_BID", "INCREASE_BUDGET", "HARVEST_KEYWORD"}
EFFICIENCY_DECISIONS = {"ADD_NEGATIVE_KEYWORD", "REDUCE_BID", "DECREASE_BUDGET", "PAUSE_CAMPAIGN"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value if value is not None else default)
    except Exception:
        return default


def _risk_value(risk: Any) -> str:
    value = str(risk or "MEDIUM").upper()
    return value if value in RISK_PENALTY else "MEDIUM"


def _payload(action: dict[str, Any]) -> dict[str, Any]:
    payload = action.get("payload")
    return payload if isinstance(payload, dict) else {}


class ExecutivePriorityEngine:
    @staticmethod
    def build_priorities(
        objective: str | None = None,
        window: str = "latest",
        country_code: str | None = None,
        profile_id: str | None = None,
        max_priorities: int = 10,
    ) -> dict[str, Any]:
        objective_config = BusinessObjectives.get(objective)
        context = resolve_data_context(window=window, country_code=country_code, profile_id=profile_id)

        plan = build_business_plan(
            objective=objective_config.get("label"),
            window=window,
            country_code=country_code,
            profile_id=profile_id,
            max_actions=30,
            min_confidence=60,
            include_high_risk=objective_config.get("risk_tolerance") in ["HIGH", "MEDIUM_HIGH"],
        )
        simulation = simulate_business_plan(plan)
        optimizer_result = run_all_optimizers(window=window, country_code=country_code, profile_id=profile_id)
        marketplace_summary = get_marketplace_summary_for_mission_control(country_code=country_code, profile_id=profile_id)

        candidate_actions = list(plan.get("actions", []) or [])
        existing_signatures = {ExecutivePriorityEngine._signature(item) for item in candidate_actions}

        for decision in optimizer_result.get("decisions", []) or []:
            signature = ExecutivePriorityEngine._signature(decision)
            if signature and signature not in existing_signatures:
                candidate_actions.append(decision)
                existing_signatures.add(signature)

        priorities = [
            ExecutivePriorityEngine._priority_from_action(action, objective_config, idx + 1)
            for idx, action in enumerate(candidate_actions)
        ]
        priorities = [item for item in priorities if item]
        priorities.sort(key=lambda item: item.get("executive_score") or 0, reverse=True)
        priorities = priorities[: max(1, min(max_priorities, 50))]

        strategic_signals = ExecutivePriorityEngine._strategic_signals(marketplace_summary, optimizer_result, plan)

        return {
            "status": "OK",
            "version": "8.0",
            "data_context": context,
            "objective": objective_config,
            "priority_count": len(priorities),
            "priorities": priorities,
            "strategic_signals": strategic_signals,
            "plan_summary": {
                "mission": plan.get("mission"),
                "included_action_count": plan.get("included_action_count"),
                "excluded_action_count": plan.get("excluded_action_count"),
                "expected_monthly_impact": plan.get("expected_monthly_impact"),
                "confidence": plan.get("confidence"),
                "risk": plan.get("risk"),
            },
            "simulation": simulation,
            "optimizer_summary": {
                "optimizer_count": optimizer_result.get("optimizer_count"),
                "opportunity_count": optimizer_result.get("opportunity_count"),
                "decision_count": optimizer_result.get("decision_count"),
            },
            "narrative": ExecutivePriorityEngine._priority_narrative(priorities, objective_config, strategic_signals),
        }

    @staticmethod
    def _signature(action: dict[str, Any]) -> str:
        payload = _payload(action)
        return "|".join([
            str(action.get("decision") or ""),
            str(action.get("decision_id") or action.get("id") or ""),
            str(payload.get("campaign_id") or action.get("campaign_id") or ""),
            str(payload.get("keyword_id") or action.get("keyword_id") or ""),
            str(payload.get("search_term") or action.get("search_term") or ""),
        ])

    @staticmethod
    def _priority_from_action(action: dict[str, Any], objective_config: dict[str, Any], fallback_rank: int) -> dict[str, Any]:
        decision_type = action.get("decision")
        confidence = _safe_float(action.get("confidence"))
        impact = _safe_float(action.get("estimated_monthly_impact"))
        risk = _risk_value(action.get("risk"))
        payload = _payload(action)

        if not decision_type:
            return {}

        score = ExecutivePriorityEngine._score_action(
            decision_type=decision_type,
            confidence=confidence,
            impact=impact,
            risk=risk,
            objective_config=objective_config,
        )

        why = ExecutivePriorityEngine._why_this_matters(decision_type, impact, confidence, risk, objective_config)

        return {
            "rank_hint": fallback_rank,
            "executive_score": score,
            "decision_id": action.get("decision_id") or action.get("id"),
            "decision": decision_type,
            "recommended_action": action.get("recommended_action"),
            "campaign_name": action.get("campaign_name") or payload.get("campaign_name"),
            "campaign_id": action.get("campaign_id") or payload.get("campaign_id"),
            "search_term": action.get("search_term") or payload.get("search_term"),
            "country_code": action.get("country_code") or payload.get("country_code"),
            "marketplace": action.get("marketplace") or payload.get("marketplace"),
            "estimated_monthly_impact": round(impact, 2),
            "confidence": confidence,
            "risk": risk,
            "priority_class": ExecutivePriorityEngine._priority_class(score),
            "why_this_matters": why,
            "next_step": ExecutivePriorityEngine._next_step(action),
            "objective_alignment": ExecutivePriorityEngine._objective_alignment(decision_type, objective_config),
        }

    @staticmethod
    def _score_action(
        decision_type: str,
        confidence: float,
        impact: float,
        risk: str,
        objective_config: dict[str, Any],
    ) -> float:
        weights = objective_config.get("weights") or {}
        impact_score = min(max(impact, 0) / 10, 40)  # $400/mo maps to 40 points; capped.
        confidence_score = max(0, min(confidence, 100))
        risk_score = max(0, 100 - RISK_PENALTY.get(risk, 12))

        growth_bonus = 100 if decision_type in GROWTH_DECISIONS else 40
        efficiency_bonus = 100 if decision_type in EFFICIENCY_DECISIONS else 50
        cash_bonus = 100 if decision_type in {"ADD_NEGATIVE_KEYWORD", "REDUCE_BID", "DECREASE_BUDGET"} else 35
        learning_bonus = 80 if decision_type in {"HARVEST_KEYWORD", "INCREASE_BID", "INCREASE_BUDGET"} else 50
        stability_bonus = 80 if risk == "LOW" else 50
        preferred_bonus = 8 if decision_type in (objective_config.get("preferred_decisions") or []) else 0

        score = (
            impact_score * 2.5 * _safe_float(weights.get("impact"), 0.35)
            + confidence_score * _safe_float(weights.get("confidence"), 0.20)
            + risk_score * _safe_float(weights.get("risk"), 0.20)
            + growth_bonus * _safe_float(weights.get("growth"), 0)
            + efficiency_bonus * _safe_float(weights.get("efficiency"), 0)
            + cash_bonus * _safe_float(weights.get("cash_protection"), 0)
            + learning_bonus * _safe_float(weights.get("learning"), 0)
            + stability_bonus * _safe_float(weights.get("stability"), 0)
            + preferred_bonus
        )
        return round(max(0, min(score, 100)), 2)

    @staticmethod
    def _priority_class(score: float) -> str:
        if score >= 80:
            return "EXECUTIVE_PRIORITY"
        if score >= 65:
            return "HIGH_VALUE"
        if score >= 45:
            return "REVIEW"
        return "MONITOR"

    @staticmethod
    def _objective_alignment(decision_type: str, objective_config: dict[str, Any]) -> str:
        if decision_type in (objective_config.get("preferred_decisions") or []):
            return "STRONG"
        if decision_type in GROWTH_DECISIONS and "growth" in (objective_config.get("weights") or {}):
            return "GOOD"
        if decision_type in EFFICIENCY_DECISIONS and "efficiency" in (objective_config.get("weights") or {}):
            return "GOOD"
        return "NEUTRAL"

    @staticmethod
    def _why_this_matters(decision_type: str, impact: float, confidence: float, risk: str, objective_config: dict[str, Any]) -> list[str]:
        reasons = [
            f"Aligned to objective: {objective_config.get('label')}.",
            f"Estimated monthly impact: {round(impact, 2)}.",
            f"Confidence: {round(confidence, 2)}%; risk: {risk}.",
        ]
        if decision_type in EFFICIENCY_DECISIONS:
            reasons.append("This is an efficiency action intended to protect margin or reduce wasted spend.")
        if decision_type in GROWTH_DECISIONS:
            reasons.append("This is a growth action intended to scale what appears to be working.")
        return reasons

    @staticmethod
    def _next_step(action: dict[str, Any]) -> str:
        decision_id = action.get("decision_id") or action.get("id")
        if decision_id:
            return f"Review decision {decision_id}; approve or execute through the existing decision workflow."
        return "Review the generated recommendation, acknowledge it to create a stable decision ID, then use the approval workflow."

    @staticmethod
    def _strategic_signals(marketplace_summary: dict[str, Any], optimizer_result: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        combined = marketplace_summary.get("combined") if isinstance(marketplace_summary, dict) else {}
        if isinstance(combined, dict):
            acos = combined.get("acos")
            roas = combined.get("roas")
            if acos is not None and _safe_float(acos) > 100:
                signals.append({
                    "signal": "ACOS_PRESSURE",
                    "severity": "HIGH",
                    "message": f"Combined ACOS is {acos}%, so efficiency actions deserve executive attention.",
                })
            if roas is not None and _safe_float(roas) >= 3:
                signals.append({
                    "signal": "SCALING_OPPORTUNITY",
                    "severity": "MEDIUM",
                    "message": f"Combined ROAS is {roas}, suggesting there may be room to scale selected winners.",
                })

        needs_attention = marketplace_summary.get("needs_attention") if isinstance(marketplace_summary, dict) else None
        if isinstance(needs_attention, dict):
            signals.append({
                "signal": "WEAKEST_MARKETPLACE",
                "severity": "MEDIUM",
                "message": f"{needs_attention.get('label')} is currently the weakest marketplace by health score.",
                "marketplace": needs_attention,
            })

        if _safe_int(optimizer_result.get("decision_count")) > _safe_int(plan.get("included_action_count")):
            signals.append({
                "signal": "UNPLANNED_OPTIMIZER_OUTPUT",
                "severity": "LOW",
                "message": "Optimizers produced more possible decisions than are currently included in the business plan.",
            })

        if not signals:
            signals.append({
                "signal": "STABLE_MONITORING",
                "severity": "LOW",
                "message": "No major executive-level strategic alerts were detected.",
            })

        return signals

    @staticmethod
    def _priority_narrative(priorities: list[dict[str, Any]], objective_config: dict[str, Any], strategic_signals: list[dict[str, Any]]) -> str:
        if not priorities:
            return f"No executive priorities were found for {objective_config.get('label')}. Continue monitoring."
        top = priorities[0]
        return (
            f"Top executive priority for {objective_config.get('label')} is {top.get('decision')} "
            f"with score {top.get('executive_score')} and estimated monthly impact "
            f"{top.get('estimated_monthly_impact')}. {len(strategic_signals)} strategic signals were detected."
        )
