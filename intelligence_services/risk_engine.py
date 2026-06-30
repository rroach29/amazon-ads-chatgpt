"""
Business OS v6.2
Risk Engine

Thin shared wrapper around the existing business risk engine. Keeping this as a
service lets future optimizers call one stable interface while the underlying
risk model evolves.
"""

from decision_risk_engine import assess_decision_risk


class RiskEngine:
    @staticmethod
    def evaluate(decision, confidence, estimated_monthly_impact, payload=None):
        return assess_decision_risk(
            decision=decision,
            confidence=confidence,
            estimated_monthly_impact=estimated_monthly_impact,
            payload=payload or {},
        )
