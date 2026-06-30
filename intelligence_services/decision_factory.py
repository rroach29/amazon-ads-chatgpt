"""
Business OS v8.3
Decision Factory with Decision Provenance

Creates standardized legacy-compatible decision dictionaries while preserving
where every decision came from: optimizer identity, optimizer version, platform
version, business objective, data context, and source opportunity.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ai.decisions.shared import make_decision
from domain import Decision, DecisionProvenance

BUSINESS_OS_VERSION = "8.3"
DECISION_FACTORY_VERSION = "2.0"
JsonDict = Dict[str, Any]


def _as_dict(value: Any) -> JsonDict:
    return value if isinstance(value, dict) else {}


def _get_nested(mapping: JsonDict, *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping.get(key) not in (None, ""):
            return mapping.get(key)
    return None


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
        optimizer_name: Optional[str] = None,
        optimizer_version: Optional[str] = None,
        optimizer_class: Optional[str] = None,
        business_objective: Optional[str] = None,
        source_opportunity_id: Optional[str] = None,
        opportunity: Optional[JsonDict] = None,
        data_context: Optional[JsonDict] = None,
    ):
        payload = _as_dict(payload)
        opportunity = _as_dict(opportunity)

        resolved_optimizer_name = (
            optimizer_name
            or _get_nested(opportunity, "optimizer_name", "optimizer")
            or _get_nested(payload, "optimizer_name", "optimizer")
            or "unknown"
        )
        resolved_optimizer_version = (
            optimizer_version
            or opportunity.get("optimizer_version")
            or payload.get("optimizer_version")
        )
        resolved_optimizer_class = (
            optimizer_class
            or opportunity.get("optimizer_class")
            or payload.get("optimizer_class")
        )
        resolved_source_opportunity_id = (
            source_opportunity_id
            or opportunity.get("opportunity_id")
            or payload.get("source_opportunity_id")
            or payload.get("opportunity_id")
        )
        resolved_data_context = (
            data_context
            or payload.get("data_window")
            or opportunity.get("data_context")
            or opportunity.get("context")
            or {}
        )
        resolved_business_objective = (
            business_objective
            or payload.get("business_objective")
            or opportunity.get("business_objective")
            or "MAXIMIZE_PROFIT"
        )

        if evidence is not None:
            payload.setdefault("evidence", evidence)
        payload.setdefault("optimizer_name", resolved_optimizer_name)
        if resolved_optimizer_version:
            payload.setdefault("optimizer_version", resolved_optimizer_version)
        if resolved_optimizer_class:
            payload.setdefault("optimizer_class", resolved_optimizer_class)
        if resolved_source_opportunity_id:
            payload.setdefault("source_opportunity_id", resolved_source_opportunity_id)
        payload.setdefault("business_objective", resolved_business_objective)
        payload.setdefault("business_os_version", BUSINESS_OS_VERSION)
        payload.setdefault("decision_factory_version", DECISION_FACTORY_VERSION)

        provenance = DecisionProvenance(
            optimizer_name=resolved_optimizer_name,
            optimizer_version=resolved_optimizer_version,
            optimizer_class=resolved_optimizer_class,
            business_os_version=BUSINESS_OS_VERSION,
            decision_factory_version=DECISION_FACTORY_VERSION,
            data_context=resolved_data_context if isinstance(resolved_data_context, dict) else {},
            business_objective=resolved_business_objective,
            source_opportunity_id=resolved_source_opportunity_id,
        )

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
        item.setdefault("schema_version", BUSINESS_OS_VERSION)
        item.setdefault("optimizer_name", resolved_optimizer_name)
        if resolved_optimizer_version:
            item.setdefault("optimizer_version", resolved_optimizer_version)
        if resolved_optimizer_class:
            item.setdefault("optimizer_class", resolved_optimizer_class)
        item.setdefault("business_os_version", BUSINESS_OS_VERSION)
        item.setdefault("decision_factory_version", DECISION_FACTORY_VERSION)
        item.setdefault("business_objective", resolved_business_objective)
        if resolved_source_opportunity_id:
            item.setdefault("source_opportunity_id", resolved_source_opportunity_id)
        item.setdefault("provenance", provenance.to_dict())
        if evidence is not None:
            item.setdefault("evidence", evidence)

        # Validate once through the domain contract, then return the legacy dict.
        domain_decision = Decision.from_legacy(item)
        item.setdefault("stable_id", domain_decision.stable_id)
        item.setdefault("created_at", domain_decision.created_at)
        item.setdefault("generated_at", provenance.generated_at)

        return item
