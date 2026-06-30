"""
Business OS v8.2 — Domain Adapters

Small adapter helpers that let the platform gradually move from dictionaries to
validated domain models without breaking existing routes or Swagger responses.
"""

from __future__ import annotations

from typing import Any, Iterable, List

from .models import Decision, Evidence, ImpactEstimate, Opportunity, Plan, RiskAssessment


def to_evidence(value: Any) -> List[Evidence]:
    if not value:
        return []
    if isinstance(value, Evidence):
        return [value]
    if isinstance(value, dict):
        return [Evidence(**value)]
    if isinstance(value, list):
        return [Evidence(**item) if isinstance(item, dict) else item for item in value if isinstance(item, (dict, Evidence))]
    return []


def opportunity_from_dict(item: dict[str, Any]) -> Opportunity:
    return Opportunity.from_legacy(item or {})


def decision_from_dict(item: dict[str, Any]) -> Decision:
    return Decision.from_legacy(item or {})


def opportunities_from_dicts(items: Iterable[dict[str, Any]]) -> List[Opportunity]:
    return [opportunity_from_dict(item) for item in (items or []) if isinstance(item, dict)]


def decisions_from_dicts(items: Iterable[dict[str, Any]]) -> List[Decision]:
    return [decision_from_dict(item) for item in (items or []) if isinstance(item, dict)]


def domain_response(model: Any) -> dict[str, Any]:
    if hasattr(model, "to_dict"):
        return model.to_dict()
    if isinstance(model, list):
        return [domain_response(item) for item in model]
    if isinstance(model, dict):
        return model
    return {"value": model}
