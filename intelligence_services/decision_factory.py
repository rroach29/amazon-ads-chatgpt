"""
Business OS v8.2
Decision Factory

Creates standardized decision dictionaries while attaching typed-domain metadata
for planner, analytics, and future Autonomous Planning releases.
"""

from ai.decisions.shared import make_decision
from domain import Decision


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
        optimizer_name=None,
        optimizer_version=None,
    ):
        payload = payload or {}
        if evidence is not None:
            payload.setdefault("evidence", evidence)
        if optimizer_name:
            payload.setdefault("optimizer_name", optimizer_name)
        if optimizer_version:
            payload.setdefault("optimizer_version", optimizer_version)

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
        item.setdefault("schema_version", "8.2")
        item.setdefault("optimizer_name", optimizer_name or payload.get("optimizer_name") or "unknown")
        if optimizer_version or payload.get("optimizer_version"):
            item.setdefault("optimizer_version", optimizer_version or payload.get("optimizer_version"))
        if evidence is not None:
            item.setdefault("evidence", evidence)

        # Validate once through the domain contract, then return the legacy dict.
        # If optional metadata is missing, the domain model supplies safe defaults.
        domain_decision = Decision.from_legacy(item)
        item.setdefault("stable_id", domain_decision.stable_id)
        item.setdefault("created_at", domain_decision.created_at)

        return item
