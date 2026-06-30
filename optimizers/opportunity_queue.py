"""
Business OS v6.0.0
Opportunity Queue

All optimizers emit standardized opportunities.
The queue ranks them before they become plans or execution candidates.
"""


def _safe_float(value, default=0):
    try:
        return float(value or default)
    except Exception:
        return default


def opportunity_score(confidence=70, impact=0, risk="LOW"):
    confidence = _safe_float(confidence)
    impact = _safe_float(impact)

    if risk == "LOW":
        risk_factor = 1.0
    elif risk == "MEDIUM":
        risk_factor = 0.75
    else:
        risk_factor = 0.45

    # Simple v6.0 score. Later releases can include learning, seasonality, margin, etc.
    raw_score = (confidence * 0.65) + min(impact / 10, 35)
    return round(raw_score * risk_factor, 2)


def build_opportunity(
    optimizer,
    decision,
    title,
    reason,
    confidence,
    risk,
    estimated_monthly_impact,
    payload=None,
):
    payload = payload if isinstance(payload, dict) else {}

    return {
        "optimizer": optimizer,
        "decision": decision,
        "title": title,
        "reason": reason,
        "confidence": confidence,
        "risk": risk,
        "estimated_monthly_impact": estimated_monthly_impact,
        "score": opportunity_score(
            confidence=confidence,
            impact=estimated_monthly_impact,
            risk=risk,
        ),
        "payload": payload,
    }


def sort_opportunities(opportunities):
    return sorted(
        opportunities or [],
        key=lambda item: (
            _safe_float(item.get("score")),
            _safe_float(item.get("estimated_monthly_impact")),
            _safe_float(item.get("confidence")),
        ),
        reverse=True,
    )
