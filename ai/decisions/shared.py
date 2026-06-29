def make_decision(
    decision,
    priority,
    confidence,
    risk,
    estimated_monthly_impact,
    reasoning,
    recommended_action,
    payload,
):
    return {
        "decision": decision,
        "priority": priority,
        "confidence": confidence,
        "risk": risk,
        "estimated_monthly_impact": estimated_monthly_impact,
        "reasoning": reasoning,
        "recommended_action": recommended_action,
        "payload": payload,
    }


def safe_float(value):
    return float(value or 0)


def safe_int(value):
    return int(value or 0)


def risk_from_confidence(confidence):
    if confidence >= 90:
        return "LOW"
    if confidence >= 75:
        return "MEDIUM"
    return "HIGH"


def sort_decisions(decisions):
    decisions.sort(
        key=lambda d: (
            d["priority"] != "HIGH",
            -d["confidence"],
            -d["estimated_monthly_impact"],
        )
    )
    return decisions
