"""
Business OS v5.0.4
Decision Risk Engine

Purpose:
Give decisions a more business-realistic risk rating.

The old approach often treated confidence-derived risk as the whole story.
That caused safe/reversible actions like ADD_NEGATIVE_KEYWORD to be marked HIGH
and excluded from Business Plans.

Risk should reflect:
- financial downside
- operational downside
- reversibility
- action type
- confidence
"""


ACTION_BASE_RISK = {
    "ADD_NEGATIVE_KEYWORD": "LOW",
    "HARVEST_KEYWORD": "LOW",
    "REDUCE_BID": "MEDIUM",
    "DECREASE_BUDGET": "MEDIUM",
    "SET_BUDGET": "MEDIUM",
    "INCREASE_BUDGET": "MEDIUM",
    "PAUSE_CAMPAIGN": "HIGH",
    "RESUME_CAMPAIGN": "MEDIUM",
}


def _risk_rank(risk):
    risk = str(risk or "").upper()

    if risk == "LOW":
        return 1

    if risk == "MEDIUM":
        return 2

    if risk == "HIGH":
        return 3

    return 2


def _risk_from_rank(rank):
    if rank <= 1:
        return "LOW"

    if rank == 2:
        return "MEDIUM"

    return "HIGH"


def assess_decision_risk(
    decision,
    confidence=70,
    estimated_monthly_impact=0,
    payload=None,
):
    payload = payload if isinstance(payload, dict) else {}
    action = str(decision or "").upper()
    confidence = float(confidence or 0)
    estimated_monthly_impact = float(estimated_monthly_impact or 0)

    base_risk = ACTION_BASE_RISK.get(action, "MEDIUM")
    risk_rank = _risk_rank(base_risk)

    factors = []

    # Confidence adjustment.
    if confidence >= 90:
        risk_rank -= 1
        factors.append("High confidence reduces risk.")

    elif confidence < 60:
        risk_rank += 1
        factors.append("Low confidence increases risk.")

    # Impact adjustment.
    if estimated_monthly_impact >= 1000:
        risk_rank += 1
        factors.append("Large estimated monthly impact increases review risk.")

    # Action-specific logic.
    if action == "ADD_NEGATIVE_KEYWORD":
        risk_rank = min(risk_rank, 1)
        factors.append("Negative keyword is reversible and does not increase spend.")

    if action == "HARVEST_KEYWORD":
        risk_rank = min(risk_rank, 1)
        factors.append("Keyword harvesting is additive and reversible.")

    if action == "PAUSE_CAMPAIGN":
        risk_rank = max(risk_rank, 3)
        factors.append("Pausing a campaign can immediately stop sales.")

    if action == "INCREASE_BUDGET":
        risk_rank = max(risk_rank, 2)
        factors.append("Budget increases can increase spend.")

    if action == "REDUCE_BID":
        risk_rank = max(risk_rank, 2)
        factors.append("Bid reductions may reduce traffic but are reversible.")

    risk_rank = max(1, min(3, risk_rank))
    overall_risk = _risk_from_rank(risk_rank)

    return {
        "technical_risk": "LOW",
        "financial_risk": _financial_risk(action, estimated_monthly_impact),
        "operational_risk": _operational_risk(action),
        "reversibility": _reversibility(action),
        "overall_risk": overall_risk,
        "base_risk": base_risk,
        "confidence": confidence,
        "estimated_monthly_impact": estimated_monthly_impact,
        "factors": factors,
    }


def _financial_risk(action, impact):
    if action in ["INCREASE_BUDGET", "SET_BUDGET"]:
        return "MEDIUM"

    if action == "PAUSE_CAMPAIGN":
        return "HIGH"

    if impact >= 1000:
        return "MEDIUM"

    return "LOW"


def _operational_risk(action):
    if action == "PAUSE_CAMPAIGN":
        return "HIGH"

    if action in ["REDUCE_BID", "DECREASE_BUDGET", "INCREASE_BUDGET", "SET_BUDGET"]:
        return "MEDIUM"

    return "LOW"


def _reversibility(action):
    if action in ["ADD_NEGATIVE_KEYWORD", "HARVEST_KEYWORD", "REDUCE_BID", "INCREASE_BUDGET", "DECREASE_BUDGET", "SET_BUDGET"]:
        return "HIGH"

    if action == "PAUSE_CAMPAIGN":
        return "MEDIUM"

    return "MEDIUM"


def risk_for_decision(
    decision,
    confidence=70,
    estimated_monthly_impact=0,
    payload=None,
):
    return assess_decision_risk(
        decision=decision,
        confidence=confidence,
        estimated_monthly_impact=estimated_monthly_impact,
        payload=payload,
    )["overall_risk"]
