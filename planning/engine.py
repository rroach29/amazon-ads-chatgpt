"""Business OS v8.4 — Executive Planning Engine.

Builds objective-aware executive plans from optimizer output while preserving the
existing approval/execution workflow. This is planning only: no live execution is
performed here.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable
from uuid import uuid4

from business_data_context import resolve_data_context
from domain import ActionGroup, Decision, Initiative, Objective, Plan
from executive.objectives import BusinessObjectives
from optimizers.optimizer_registry import run_all_optimizers


RISK_ORDER = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
DECISION_FAMILIES = {
    "ADD_NEGATIVE_KEYWORD": "Reduce wasted spend",
    "REDUCE_BID": "Reduce wasted spend",
    "DECREASE_BUDGET": "Protect cash and reduce waste",
    "INCREASE_BID": "Scale proven demand",
    "INCREASE_BUDGET": "Scale profitable campaigns",
    "HARVEST_KEYWORD": "Harvest proven demand",
    "PAUSE_CAMPAIGN": "Protect cash and reduce waste",
    "INCREASE_PLACEMENT_MODIFIER": "Scale proven demand",
    "REDUCE_PLACEMENT_MODIFIER": "Reduce wasted spend",
}
GROWTH_DECISIONS = {"INCREASE_BID", "INCREASE_BUDGET", "HARVEST_KEYWORD", "INCREASE_PLACEMENT_MODIFIER"}
EFFICIENCY_DECISIONS = {"ADD_NEGATIVE_KEYWORD", "REDUCE_BID", "DECREASE_BUDGET", "PAUSE_CAMPAIGN", "REDUCE_PLACEMENT_MODIFIER"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except Exception:
        return default


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _risk_value(value: Any) -> str:
    risk = str(value or "MEDIUM").upper()
    return risk if risk in RISK_ORDER else "MEDIUM"


def _payload(item: dict[str, Any]) -> dict[str, Any]:
    payload = item.get("payload")
    return payload if isinstance(payload, dict) else {}


def _campaign_key(item: dict[str, Any]) -> str:
    payload = _payload(item)
    return _safe_str(
        payload.get("campaign_id") or item.get("campaign_id") or payload.get("campaign_name") or item.get("campaign_name") or "business",
        "business",
    )


def _campaign_label(item: dict[str, Any]) -> str:
    payload = _payload(item)
    return _safe_str(payload.get("campaign_name") or item.get("campaign_name") or "Business-wide optimization", "Business-wide optimization")


def _decision_type(item: dict[str, Any]) -> str:
    return _safe_str(item.get("decision") or item.get("decision_type") or "UNKNOWN", "UNKNOWN").upper()


def _signature(item: dict[str, Any]) -> str:
    payload = _payload(item)
    return "|".join(
        [
            _decision_type(item),
            _safe_str(item.get("stable_id") or item.get("decision_id") or item.get("id")),
            _safe_str(payload.get("campaign_id") or item.get("campaign_id")),
            _safe_str(payload.get("keyword_id") or item.get("keyword_id")),
            _safe_str(payload.get("search_term") or item.get("search_term")),
        ]
    )


class ExecutivePlanningEngine:
    """Create plan/initiative/action-group objects from optimizer decisions."""

    @staticmethod
    def build_plan(
        objective: str | None = None,
        window: str = "latest",
        country_code: str | None = None,
        profile_id: str | None = None,
        max_actions: int = 20,
        max_initiatives: int = 8,
    ) -> dict[str, Any]:
        objective_config = BusinessObjectives.get(objective)
        context = resolve_data_context(window=window, country_code=country_code, profile_id=profile_id)
        optimizer_result = run_all_optimizers(window=window, country_code=country_code, profile_id=profile_id)

        raw_decisions = ExecutivePlanningEngine._dedupe(optimizer_result.get("decisions", []) or [])
        raw_decisions = [item for item in raw_decisions if isinstance(item, dict)]
        raw_decisions.sort(
            key=lambda item: ExecutivePlanningEngine._action_score(item, objective_config),
            reverse=True,
        )
        raw_decisions = raw_decisions[: max(1, min(max_actions, 100))]

        conflict_report = ExecutivePlanningEngine.detect_conflicts(raw_decisions)
        initiatives = ExecutivePlanningEngine._build_initiatives(
            raw_decisions=raw_decisions,
            objective_config=objective_config,
            max_initiatives=max_initiatives,
        )

        plan = ExecutivePlanningEngine._plan_from_initiatives(
            initiatives=initiatives,
            objective_config=objective_config,
        )

        return {
            "status": "OK",
            "version": "8.4",
            "schema_version": "8.4",
            "data_context": context,
            "objective": objective_config,
            "plan": plan.to_dict(),
            "initiative_count": len(initiatives),
            "action_count": sum(len(group.actions) for initiative in initiatives for group in initiative.action_groups),
            "conflicts": conflict_report,
            "optimizer_summary": {
                "optimizer_count": optimizer_result.get("optimizer_count"),
                "opportunity_count": optimizer_result.get("opportunity_count"),
                "decision_count": optimizer_result.get("decision_count"),
            },
            "approval_model": {
                "approval_required": True,
                "execution_is_not_performed_by_this_endpoint": True,
                "use_existing_decision_workflow": True,
            },
            "narrative": ExecutivePlanningEngine._narrative(plan, conflict_report),
        }

    @staticmethod
    def initiatives(
        objective: str | None = None,
        window: str = "latest",
        country_code: str | None = None,
        profile_id: str | None = None,
        max_actions: int = 20,
    ) -> dict[str, Any]:
        result = ExecutivePlanningEngine.build_plan(
            objective=objective,
            window=window,
            country_code=country_code,
            profile_id=profile_id,
            max_actions=max_actions,
        )
        plan = result.get("plan") or {}
        return {
            "status": result.get("status"),
            "version": "8.4",
            "objective": result.get("objective"),
            "initiative_count": result.get("initiative_count"),
            "initiatives": plan.get("initiatives", []),
            "narrative": result.get("narrative"),
        }

    @staticmethod
    def conflicts(
        window: str = "latest",
        country_code: str | None = None,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        optimizer_result = run_all_optimizers(window=window, country_code=country_code, profile_id=profile_id)
        return {
            "status": "OK",
            "version": "8.4",
            "data_context": optimizer_result.get("context"),
            "conflicts": ExecutivePlanningEngine.detect_conflicts(optimizer_result.get("decisions", []) or []),
        }

    @staticmethod
    def detect_conflicts(items: Iterable[dict[str, Any]]) -> dict[str, Any]:
        by_campaign: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            if isinstance(item, dict):
                by_campaign[_campaign_key(item)].append(item)

        conflicts = []
        for campaign_key, campaign_items in by_campaign.items():
            types = {_decision_type(item) for item in campaign_items}
            if types & GROWTH_DECISIONS and types & EFFICIENCY_DECISIONS:
                conflicts.append(
                    {
                        "conflict_id": str(uuid4()),
                        "scope": "campaign",
                        "campaign_key": campaign_key,
                        "campaign_name": _campaign_label(campaign_items[0]),
                        "growth_actions": sorted(types & GROWTH_DECISIONS),
                        "efficiency_actions": sorted(types & EFFICIENCY_DECISIONS),
                        "resolution": "Review as a grouped initiative. Prefer low-risk efficiency actions before scaling unless the active objective favors growth.",
                    }
                )

        return {
            "status": "OK",
            "count": len(conflicts),
            "items": conflicts,
            "has_conflicts": bool(conflicts),
        }

    @staticmethod
    def _dedupe(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        output: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            sig = _signature(item)
            if sig in seen:
                continue
            seen.add(sig)
            output.append(item)
        return output

    @staticmethod
    def _build_initiatives(
        raw_decisions: list[dict[str, Any]],
        objective_config: dict[str, Any],
        max_initiatives: int,
    ) -> list[Initiative]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in raw_decisions:
            family = DECISION_FAMILIES.get(_decision_type(item), "Review optimization opportunity")
            campaign = _campaign_label(item)
            grouped[f"{family} :: {campaign}"].append(item)

        initiatives: list[Initiative] = []
        for key, actions in grouped.items():
            family, campaign = key.split(" :: ", 1)
            decisions = [Decision.from_legacy(item) for item in actions]
            impact = round(sum(_safe_float(item.get("estimated_monthly_impact")) for item in actions), 2)
            confidence = round(sum(_safe_float(item.get("confidence")) for item in actions) / max(len(actions), 1), 2)
            risk = ExecutivePlanningEngine._max_risk([_risk_value(item.get("risk")) for item in actions])
            score = round(sum(ExecutivePlanningEngine._action_score(item, objective_config) for item in actions) / max(len(actions), 1), 2)

            action_group = ActionGroup(
                title=family,
                actions=decisions,
                estimated_monthly_impact=impact,
                confidence=confidence,
                risk=risk,
                execution_phase="REVIEW",
            )
            initiatives.append(
                Initiative(
                    title=f"{family}: {campaign}",
                    objective=objective_config.get("label"),
                    action_groups=[action_group],
                    estimated_monthly_impact=impact,
                    confidence=confidence,
                    risk=risk,
                    priority_score=score,
                    narrative=ExecutivePlanningEngine._initiative_narrative(family, campaign, actions, impact, confidence, risk),
                )
            )

        initiatives.sort(key=lambda item: item.priority_score, reverse=True)
        return initiatives[: max(1, min(max_initiatives, 50))]

    @staticmethod
    def _plan_from_initiatives(initiatives: list[Initiative], objective_config: dict[str, Any]) -> Plan:
        impact = round(sum(item.estimated_monthly_impact for item in initiatives), 2)
        confidence = round(sum(item.confidence for item in initiatives) / max(len(initiatives), 1), 2) if initiatives else 0
        risk = ExecutivePlanningEngine._max_risk([item.risk for item in initiatives]) if initiatives else "LOW"
        return Plan(
            title="Executive Business Plan",
            objective=Objective(
                objective_id=objective_config.get("key") or "maximize_profit",
                label=objective_config.get("label") or "Maximize Profit",
                description=objective_config.get("description") or "Objective-aware executive plan.",
                risk_tolerance=_risk_value(objective_config.get("risk_tolerance")),
            ),
            initiatives=initiatives,
            estimated_monthly_impact=impact,
            confidence=confidence,
            risk=risk,
            schema_version="8.4",
        )

    @staticmethod
    def _action_score(item: dict[str, Any], objective_config: dict[str, Any]) -> float:
        impact = max(0, _safe_float(item.get("estimated_monthly_impact")))
        confidence = max(0, min(_safe_float(item.get("confidence")), 100))
        risk = _risk_value(item.get("risk"))
        decision_type = _decision_type(item)
        weights = objective_config.get("weights") or {}

        impact_score = min(impact / 10, 40)
        risk_score = {"LOW": 100, "MEDIUM": 70, "HIGH": 25}.get(risk, 70)
        preferred_bonus = 10 if decision_type in (objective_config.get("preferred_decisions") or []) else 0
        growth_bonus = 10 if decision_type in GROWTH_DECISIONS and weights.get("growth") else 0
        efficiency_bonus = 10 if decision_type in EFFICIENCY_DECISIONS and weights.get("efficiency") else 0

        score = (
            impact_score * 2.5 * _safe_float(weights.get("impact"), 0.40)
            + confidence * _safe_float(weights.get("confidence"), 0.25)
            + risk_score * _safe_float(weights.get("risk"), 0.20)
            + preferred_bonus
            + growth_bonus
            + efficiency_bonus
        )
        return round(max(0, min(score, 100)), 2)

    @staticmethod
    def _max_risk(risks: Iterable[Any]) -> str:
        values = [_risk_value(risk) for risk in risks]
        if not values:
            return "LOW"
        return max(values, key=lambda risk: RISK_ORDER.get(risk, 2))

    @staticmethod
    def _initiative_narrative(family: str, campaign: str, actions: list[dict[str, Any]], impact: float, confidence: float, risk: str) -> str:
        return f"{family} for {campaign}: {len(actions)} action(s), estimated monthly impact {impact}, confidence {confidence}, risk {risk}."

    @staticmethod
    def _narrative(plan: Plan, conflict_report: dict[str, Any]) -> str:
        if not plan.initiatives:
            return "No executive initiatives are available from the current optimizer signals."
        top = plan.initiatives[0]
        conflict_note = " No conflicts detected." if not conflict_report.get("has_conflicts") else f" {conflict_report.get('count')} conflict(s) require review."
        return f"Top initiative: {top.title}. Combined estimated monthly impact: {plan.estimated_monthly_impact}." + conflict_note
