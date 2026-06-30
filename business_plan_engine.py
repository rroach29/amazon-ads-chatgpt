"""
Business OS v5.0.4
Business Plan Engine — Risk Alignment

Updates:
- Uses payload.risk_assessment.overall_risk when present.
- Negative keyword decisions now flow into plans when their assessed risk is LOW.
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

SUPPORTED_PLAN_ACTIONS = set(ACTION_WEIGHTS.keys())


def _safe_float(value, default=0):
    try:
        return float(value or default)
    except Exception:
        return default


def _effective_risk(action):
    payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
    assessment = payload.get("risk_assessment") if isinstance(payload.get("risk_assessment"), dict) else {}

    return assessment.get("overall_risk") or action.get("risk")


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
    effective_risk = _effective_risk(action)

    return {
        "decision_id": action.get("id"),
        "decision": action.get("decision"),
        "priority": action.get("priority"),
        "confidence": action.get("confidence"),
        "risk": effective_risk,
        "original_risk": action.get("risk"),
        "risk_assessment": payload.get("risk_assessment"),
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


def _decision_exclusion_reasons(
    action,
    min_confidence=70,
    include_high_risk=False,
    allowed_actions=None,
):
    reasons = []

    allowed_actions = allowed_actions or SUPPORTED_PLAN_ACTIONS

    decision_type = action.get("decision")
    confidence = _safe_float(action.get("confidence"))
    risk = str(_effective_risk(action) or "").upper()
    payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}

    if decision_type not in allowed_actions:
        reasons.append(f"Unsupported plan action: {decision_type}")

    if confidence < min_confidence:
        reasons.append(f"Confidence {confidence:g} is below minimum {min_confidence}.")

    if risk == "HIGH" and not include_high_risk:
        reasons.append("Risk HIGH is excluded by plan settings.")

    if not payload:
        reasons.append("Decision payload is missing.")

    if decision_type in ["PAUSE_CAMPAIGN", "INCREASE_BUDGET", "DECREASE_BUDGET", "SET_BUDGET"]:
        if not payload.get("campaign_id"):
            reasons.append("Campaign action is missing campaign_id.")

    if decision_type in ["ADD_NEGATIVE_KEYWORD", "HARVEST_KEYWORD"]:
        if not payload.get("search_term"):
            reasons.append("Search-term action is missing search_term.")

    if decision_type in ["REDUCE_BID", "SET_BID"]:
        if not payload.get("keyword_id"):
            reasons.append("Bid action is missing keyword_id.")

    return reasons


def _filter_actions_with_explainability(
    raw_actions,
    max_actions=20,
    min_confidence=70,
    include_high_risk=False,
    allowed_actions=None,
):
    included = []
    excluded = []

    action_payloads = [_action_payload(action) for action in raw_actions]

    for raw_action, action in zip(raw_actions, action_payloads):
        reasons = _decision_exclusion_reasons(
            raw_action,
            min_confidence=min_confidence,
            include_high_risk=include_high_risk,
            allowed_actions=allowed_actions,
        )

        if reasons:
            excluded.append({
                "decision_id": raw_action.get("id"),
                "decision": raw_action.get("decision"),
                "recommended_action": raw_action.get("recommended_action"),
                "confidence": raw_action.get("confidence"),
                "risk": _effective_risk(raw_action),
                "original_risk": raw_action.get("risk"),
                "estimated_monthly_impact": raw_action.get("estimated_monthly_impact"),
                "reasons": reasons,
                "payload_summary": {
                    "campaign_id": action.get("campaign_id"),
                    "campaign_name": action.get("campaign_name"),
                    "keyword_id": action.get("keyword_id"),
                    "search_term": action.get("search_term"),
                    "country_code": action.get("country_code"),
                    "data_window": action.get("data_window"),
                    "risk_assessment": action.get("risk_assessment"),
                },
            })
            continue

        included.append(action)

    included = sorted(
        included,
        key=lambda item: (
            _safe_float(item.get("estimated_monthly_impact")),
            _safe_float(item.get("confidence")),
        ),
        reverse=True,
    )

    overflow = included[max_actions:]
    included = included[:max_actions]

    for action in overflow:
        excluded.append({
            "decision_id": action.get("decision_id"),
            "decision": action.get("decision"),
            "recommended_action": action.get("recommended_action"),
            "confidence": action.get("confidence"),
            "risk": action.get("risk"),
            "original_risk": action.get("original_risk"),
            "estimated_monthly_impact": action.get("estimated_monthly_impact"),
            "reasons": [f"Excluded because max_actions={max_actions} was reached."],
            "payload_summary": {
                "campaign_id": action.get("campaign_id"),
                "campaign_name": action.get("campaign_name"),
                "keyword_id": action.get("keyword_id"),
                "search_term": action.get("search_term"),
                "country_code": action.get("country_code"),
                "data_window": action.get("data_window"),
                "risk_assessment": action.get("risk_assessment"),
            },
        })

    return included, excluded


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

    decision_response = get_decision_history(
        status="OPEN",
        limit=100,
        current_window_only=True,
        include_legacy=False,
    )

    raw_actions = decision_response.get("items", [])

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

    selected_actions, excluded_actions = _filter_actions_with_explainability(
        raw_actions=raw_actions,
        max_actions=max_actions,
        min_confidence=min_confidence,
        include_high_risk=include_high_risk,
        allowed_actions=SUPPORTED_PLAN_ACTIONS,
    )

    total_impact = round(
        sum(_safe_float(action.get("estimated_monthly_impact")) for action in selected_actions),
        2,
    )

    return {
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
        "included_action_count": len(selected_actions),
        "excluded_action_count": len(excluded_actions),
        "expected_monthly_impact": total_impact,
        "confidence": _weighted_confidence(selected_actions),
        "risk": _plan_risk(selected_actions),
        "approval_required": True,
        "execution_mode": "PLAN_ONLY",
        "success_metrics": _success_metrics(selected_actions),
        "grouped_actions": _group_actions(selected_actions),
        "actions": selected_actions,
        "excluded_actions": excluded_actions,
        "diagnostics": {
            "supported_plan_actions": sorted(list(SUPPORTED_PLAN_ACTIONS)),
            "min_confidence": min_confidence,
            "include_high_risk": include_high_risk,
            "max_actions": max_actions,
            "decision_history_count": decision_response.get("count"),
            "decision_history_current_window_only": decision_response.get("current_window_only"),
            "data_context": data_context,
            "risk_source": "payload.risk_assessment.overall_risk when present, otherwise decision.risk",
        },
        "constraints": {
            "min_confidence": min_confidence,
            "include_high_risk": include_high_risk,
            "max_actions": max_actions,
            "live_execution_requires_existing_execution_engine": True,
        },
        "next_steps": [
            "Review included and excluded actions.",
            "Dry-run selected actions through the execution engine.",
            "Execute live only after approval.",
            "Evaluate results after 1, 3, and 7 days.",
        ],
    }


def simulate_business_plan(plan):
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
        "available_open_decisions": plan.get("available_open_decisions"),
        "included_action_count": plan.get("included_action_count"),
        "excluded_action_count": plan.get("excluded_action_count"),
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
                "original_risk": action.get("original_risk"),
                "campaign_name": action.get("campaign_name"),
                "search_term": action.get("search_term"),
            }
            for action in plan.get("actions", [])[:10]
        ],
        "excluded_actions": [
            {
                "decision_id": action.get("decision_id"),
                "decision": action.get("decision"),
                "recommended_action": action.get("recommended_action"),
                "confidence": action.get("confidence"),
                "risk": action.get("risk"),
                "original_risk": action.get("original_risk"),
                "reasons": action.get("reasons"),
            }
            for action in plan.get("excluded_actions", [])[:10]
        ],
    }
