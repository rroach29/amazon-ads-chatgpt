"""
Business OS v6.2
Decision Factory

Creates standardized decision dictionaries while preserving compatibility with
existing route and execution code.
"""

from ai.decisions.shared import make_decision


class DecisionFactory:
    @staticmethod
    def create(
        decision,
        priority,
        confidence,
        risk,
        estimated_monthly_impact,
        reasoning,
        recommended_action,
        payload,
        evidence=None,
        lifecycle_state="NEW",
    ):
        payload = payload or {}
        if evidence is not None:
            payload.setdefault("evidence", evidence)

        item = make_decision(
            decision=decision,
            priority=priority,
            confidence=confidence,
            risk=risk,
            estimated_monthly_impact=estimated_monthly_impact,
            reasoning=reasoning,
            recommended_action=recommended_action,
            payload=payload,
        )

        # Non-breaking metadata. Existing clients can ignore these fields.
        item.setdefault("lifecycle_state", lifecycle_state)
        item.setdefault("source", "optimizer")
        if evidence is not None:
            item.setdefault("evidence", evidence)

        return item
