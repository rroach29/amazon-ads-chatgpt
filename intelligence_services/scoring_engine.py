"""
Business OS v6.2
Scoring Engine

Produces consistent opportunity scores across optimizer types.
"""


_RISK_PENALTY = {
    "LOW": 0,
    "MEDIUM": 8,
    "HIGH": 18,
    "CRITICAL": 30,
}


class ScoringEngine:
    @staticmethod
    def opportunity_score(confidence, estimated_monthly_impact, risk="MEDIUM", strategic_weight=1.0):
        confidence = int(confidence or 0)
        impact = float(estimated_monthly_impact or 0)
        risk_key = str(risk or "MEDIUM").upper()
        penalty = _RISK_PENALTY.get(risk_key, 10)

        # Keep this intentionally simple and explainable. Impact contributes,
        # but confidence and risk dominate so the queue stays safe.
        impact_component = min(25, int(impact / 10))
        score = int((confidence + impact_component - penalty) * float(strategic_weight or 1.0))
        return max(0, min(score, 100))
