"""
Business OS v6.1.0
Shared Optimization Scoring

Centralizes queue scoring so future optimizers do not duplicate ranking logic.
"""


def safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return default


def risk_factor(risk: str) -> float:
    risk = str(risk or "MEDIUM").upper()

    if risk == "LOW":
        return 1.0
    if risk == "MEDIUM":
        return 0.75
    if risk == "HIGH":
        return 0.45

    return 0.65


def opportunity_score(confidence=70, impact=0, risk="LOW") -> float:
    confidence = safe_float(confidence)
    impact = safe_float(impact)

    # Bounded impact contribution prevents large-dollar actions from drowning
    # out lower-risk/high-confidence actions.
    raw_score = (confidence * 0.65) + min(impact / 10, 35)
    return round(raw_score * risk_factor(risk), 2)


def priority_from_confidence(confidence, risk="MEDIUM") -> str:
    confidence = safe_float(confidence)
    risk = str(risk or "MEDIUM").upper()

    if confidence >= 90 and risk == "LOW":
        return "CRITICAL"
    if confidence >= 85:
        return "HIGH"
    if confidence >= 70:
        return "MEDIUM"
    return "LOW"
