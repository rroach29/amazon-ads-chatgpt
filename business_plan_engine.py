"""
Business OS v5.0.0
Business Plan Engine

This turns individual decisions into an approval-ready operating plan.

Instead of:
- approve decision 1
- approve decision 2
- approve decision 3

The OS can now generate:
- one mission
- one plan
- grouped actions
- expected impact
- confidence
- risk
- success metrics

v5.0 does not execute plans automatically. It packages and evaluates them.
Execution remains handled by the existing execution engine.
"""

from datetime import datetime

from business_data_context import resolve_data_context
from decision_history import get_decision_history


ACTION_WEIGHTS = {
    "PAUSE_CAMPAIGN": 1.0,
    "ADD_NEGATIVE_KEYWORD": 0.9,
    "REDUCE_BID": 0.8,
    "INCREASE_BUDGET": 0.7,
    "DECREASE_BUDGET": 0.8,
    "SET_BUDGET": 0.7,
    "HARVEST_KEYWORD": 0.6,
}


def _safe_float(value, default=0):
    try:
        return float(value or default)
    except Exception:
        return default


def _safe_int(value, default=0):
    try:
        return int(value or default)
    except Exception:
        return default


def _risk_score(risk):
    risk = str(risk or "").upper()

    if risk == "LOW":
        return 1

    if risk == "MEDIUM":
        return 2

    if risk == "HIGH":
        return 3

    return 2


def _plan_risk(actions):
    if not actions:
        return "LOW"

    max_risk = max(_risk_score(action.get("risk")) for action in actions)

    if max_risk >= 3:
        return "HIGH"

    if max_risk == 2:
        return "MEDIUM"

    return "LOW"


def _weighted_confidence(actions):
    if not actions:
        return 0

    weighted_sum = 0
    total_weight = 0

    for action in actions:
        action_type = action.get("decision")
        weight = ACTION_WEIGHTS.get(action_type, 0.5)
        confidence = _safe_float(action.get("confidence"))

        weighted_sum += confidence * weight
        total_weight += weight

    if total_weight <= 0:
        return 0

    return round(weighted_sum / total_weight, 2)


def _action_payload(action):
    payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}

    return {
        "decision_id": action.get("id"),
        "decision": action.get("decision"),
        "priority": action.get("priority"),
        "confidence": action.get("confidence"),
        "risk": action.get("risk"),
        "recommended_action": action.get("recommended_action"),
        "estimated_monthly_impact": action.get("estimated_monthly_impact"),
        "campaign_id": payload.get("campaign_id"),
        "campaign_name": payload.get("campaign_name"),
        "ad_group_id": payload.get("ad_group_id"),
        "ad_group_name": payload.get("ad_group_name"),
        "keyword_id": payload.get("keyword_id"),
        "search_term": payload.get("search_term"),
        "profile_id": payload.get("profile_id"),
        "country_code": payload.get("country_code"),
        "marketplace": payload.get("marketplace"),
        "currency": payload.get("currency"),
        "data_window": payload.get("data_window"),
        "payload": payload,
    }


def _group_actions(actions):
    grouped = {}

    for action in actions:
        decision_type = action.get("decision")

        if decision_type not in grouped:
            grouped[decision_type] = {
                "decision": decision_type,
                "count": 0,
                "estimated_monthly_impact": 0,
                "average_confidence": 0,
                "actions": [],
            }

        grouped[decision_type]["count"] += 1
        grouped[decision_type]["estimated_monthly_impact"] += _safe_float(
            action.get("estimated_monthly_impact")
        )
        grouped[decision_type]["actions"].append(action)

    for decision_type, group in grouped.items():
        group["estimated_monthly_impact"] = round(group["estimated_monthly_impact"], 2)
        group["average_confidence"] = _weighted_confidence(group["actions"])

    return list(grouped.values())


def _filter_actions(actions, max_actions=20, min_confidence=70, include_high_risk=False):
    filtered = []

    for action in actions:
        confidence = _safe_float(action.get("confidence"))
        risk = str(action.get("risk") or "").upper()

        if confidence < min_confidence:
            continue

        if risk == "HIGH" and not include_high_risk:
            continue

        filtered.append(action)

    filtered = sorted(
        filtered,
        key=lambda item: (
            _safe_float(item.get("estimated_monthly_impact")),
            _safe_float(item.get("confidence")),
        ),
        reverse=True,
    )

    return filtered[:max_actions]


def _mission_for_plan(actions, objective=None):
    if objective:
        return objective

    if not actions:
        return "Maintain account stability and monitor for new opportunities."

    action_types = {action.get("decision") for action in actions}

    if "PAUSE_CAMPAIGN" in action_types or "ADD_NEGATIVE_KEYWORD" in action_types:
        return "Improve advertising efficiency by reducing wasted spend."

    if "INCREASE_BUDGET" in action_types:
        return "Scale efficient campaigns while maintaining profitability guardrails."

    if "REDUCE_BID" in action_types:
        return "Improve ACOS by reducing bids on inefficient but active targets."

    return "Improve Amazon Ads performance with controlled, approval-based optimization."


def _success_metrics(actions):
    metrics = ["Spend", "Sales", "ACOS", "ROAS", "Orders"]

    action_types = {action.get("decision") for action in actions}

    if "PAUSE_CAMPAIGN" in action_types or "ADD_NEGATIVE_KEYWORD" in action_types:
        metrics.extend(["Wasted Spend", "Clicks With No Sales"])

    if "INCREASE_BUDGET" in action_types:
        metrics.extend(["Budget Utilization", "Incremental Sales"])

    if "REDUCE_BID" in action_types:
        metrics.extend(["CPC", "Target ACOS"])

    return list(dict.fromkeys(metrics))


def build_business_plan(
    objective=None,
    window="latest",
    country_code=None,
    profile_id=None,
    max_actions=20,
    min_confidence=70,
    include_high_risk=False,
):
    data_context = resolve_data_context(
        window=window,
        country_code=country_code,
        profile_id=profile_id,
    )

    # This reads only current-window OPEN decisions after v4.0.1.
    decision_response = get_decision_history(
        status="OPEN",
        limit=100,
        current_window_only=True,
        include_legacy=False,
    )

    raw_actions = decision_response.get("items", [])

    # Optional marketplace filter at plan level.
    if country_code:
        raw_actions = [
            action for action in raw_actions
            if (action.get("payload") or {}).get("country_code") == country_code
        ]

    if profile_id:
        raw_actions = [
            action for action in raw_actions
            if str((action.get("payload") or {}).get("profile_id")) == str(profile_id)
        ]

    actions = [_action_payload(action) for action in raw_actions]
    selected_actions = _filter_actions(
        actions,
        max_actions=max_actions,
        min_confidence=min_confidence,
        include_high_risk=include_high_risk,
    )

    total_impact = round(
        sum(_safe_float(action.get("estimated_monthly_impact")) for action in selected_actions),
        2,
    )

    plan = {
        "status": "OK",
        "plan_type": "BUSINESS_OPTIMIZATION_PLAN",
        "created_at": datetime.utcnow().isoformat(),
        "mission": _mission_for_plan(selected_actions, objective=objective),
        "objective": objective,
        "planning_window": {
            "window": data_context.get("window"),
            "start_date": data_context.get("start_date"),
            "end_date": data_context.get("end_date"),
        },
        "marketplace_filter": {
            "country_code": country_code,
            "profile_id": profile_id,
        },
        "action_count": len(selected_actions),
        "available_open_decisions": len(raw_actions),
        "expected_monthly_impact": total_impact,
        "confidence": _weighted_confidence(selected_actions),
        "risk": _plan_risk(selected_actions),
        "approval_required": True,
        "execution_mode": "PLAN_ONLY",
        "success_metrics": _success_metrics(selected_actions),
        "grouped_actions": _group_actions(selected_actions),
        "actions": selected_actions,
        "constraints": {
            "min_confidence": min_confidence,
            "include_high_risk": include_high_risk,
            "max_actions": max_actions,
            "live_execution_requires_existing_execution_engine": True,
        },
        "next_steps": [
            "Review the plan.",
            "Dry-run selected actions through the execution engine.",
            "Execute live only after approval.",
            "Evaluate results after 1, 3, and 7 days.",
        ],
    }

    return plan


def simulate_business_plan(plan):
    """
    Lightweight v5.0 simulation.

    This is deliberately conservative. It uses decision estimated impact and risk
    rather than pretending to predict exact future performance.
    """
    actions = plan.get("actions", []) if isinstance(plan, dict) else []

    expected_impact = _safe_float(plan.get("expected_monthly_impact"))
    confidence = _safe_float(plan.get("confidence"))
    risk = plan.get("risk")

    confidence_factor = confidence / 100 if confidence else 0

    if risk == "HIGH":
        risk_discount = 0.5
    elif risk == "MEDIUM":
        risk_discount = 0.75
    else:
        risk_discount = 0.9

    conservative_impact = round(expected_impact * confidence_factor * risk_discount, 2)

    return {
        "status": "OK",
        "simulation_type": "CONSERVATIVE_IMPACT_ESTIMATE",
        "action_count": len(actions),
        "expected_monthly_impact": expected_impact,
        "confidence": confidence,
        "risk": risk,
        "conservative_expected_monthly_impact": conservative_impact,
        "notes": [
            "This is a conservative simulation based on current decision estimates.",
            "Future releases should use actual outcome history, profit margin, inventory, and seasonality.",
        ],
    }


def get_plan_summary(plan):
    return {
        "status": plan.get("status"),
        "mission": plan.get("mission"),
        "planning_window": plan.get("planning_window"),
        "action_count": plan.get("action_count"),
        "expected_monthly_impact": plan.get("expected_monthly_impact"),
        "confidence": plan.get("confidence"),
        "risk": plan.get("risk"),
        "grouped_actions": [
            {
                "decision": group.get("decision"),
                "count": group.get("count"),
                "estimated_monthly_impact": group.get("estimated_monthly_impact"),
                "average_confidence": group.get("average_confidence"),
            }
            for group in plan.get("grouped_actions", [])
        ],
        "top_actions": [
            {
                "decision_id": action.get("decision_id"),
                "decision": action.get("decision"),
                "recommended_action": action.get("recommended_action"),
                "estimated_monthly_impact": action.get("estimated_monthly_impact"),
                "confidence": action.get("confidence"),
                "risk": action.get("risk"),
                "campaign_name": action.get("campaign_name"),
                "search_term": action.get("search_term"),
            }
            for action in plan.get("actions", [])[:10]
        ],
    }
