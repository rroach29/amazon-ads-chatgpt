"""
Business OS v5.0.0
Mission Control

A compact executive operating view.
"""

from business_data_context import resolve_data_context
from marketplace_intelligence import get_marketplace_summary
from business_plan_engine import build_business_plan, get_plan_summary, simulate_business_plan
from decision_history import get_decision_history


def get_mission_control(
    objective=None,
    window="latest",
    country_code=None,
    profile_id=None,
):
    context = resolve_data_context(
        window=window,
        country_code=country_code,
        profile_id=profile_id,
    )

    marketplace_summary = get_marketplace_summary()

    plan = build_business_plan(
        objective=objective,
        window=window,
        country_code=country_code,
        profile_id=profile_id,
        max_actions=20,
        min_confidence=70,
        include_high_risk=False,
    )

    simulation = simulate_business_plan(plan)

    decisions = get_decision_history(
        status="OPEN",
        limit=50,
        current_window_only=True,
        include_legacy=False,
    )

    return {
        "status": "OK",
        "title": "Business OS Mission Control",
        "data_context": context,
        "mission": plan.get("mission"),
        "marketplace_summary": marketplace_summary,
        "current_plan": get_plan_summary(plan),
        "simulation": simulation,
        "open_decisions": {
            "count": decisions.get("count"),
            "current_window_only": decisions.get("current_window_only"),
        },
        "operating_mode": {
            "plan_approval_required": True,
            "live_execution_requires_confirm_live": True,
            "high_risk_actions_excluded_by_default": True,
        },
        "recommended_focus": _recommended_focus(plan, marketplace_summary),
    }


def _recommended_focus(plan, marketplace_summary):
    focus = []

    if plan.get("action_count", 0) > 0:
        focus.append({
            "priority": "HIGH",
            "focus": "Review current business plan",
            "reason": f"{plan.get('action_count')} approval-ready actions are available.",
            "expected_monthly_impact": plan.get("expected_monthly_impact"),
        })

    needs_attention = marketplace_summary.get("needs_attention") if isinstance(marketplace_summary, dict) else None

    if needs_attention:
        focus.append({
            "priority": "HIGH",
            "focus": "Review weakest marketplace",
            "reason": f"{needs_attention.get('label')} has the weakest current health score.",
            "marketplace": needs_attention,
        })

    if not focus:
        focus.append({
            "priority": "LOW",
            "focus": "Monitor",
            "reason": "No high-confidence approval-ready actions are available for the current data window.",
        })

    return focus
