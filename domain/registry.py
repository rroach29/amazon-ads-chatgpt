"""Business OS v8.2 — Domain Schema Registry."""

from __future__ import annotations

from typing import Any

from .models import (
    ActionGroup,
    Decision,
    Evidence,
    ImpactEstimate,
    Initiative,
    Objective,
    Opportunity,
    Outcome,
    Plan,
    RiskAssessment,
)

MODELS = {
    "Evidence": Evidence,
    "ImpactEstimate": ImpactEstimate,
    "RiskAssessment": RiskAssessment,
    "Opportunity": Opportunity,
    "Decision": Decision,
    "Objective": Objective,
    "ActionGroup": ActionGroup,
    "Initiative": Initiative,
    "Plan": Plan,
    "Outcome": Outcome,
}


def _schema(model: Any) -> dict[str, Any]:
    try:
        return model.model_json_schema()  # pydantic v2
    except AttributeError:
        return model.schema()  # pydantic v1


class DomainRegistry:
    @staticmethod
    def list_models() -> dict[str, Any]:
        return {
            "status": "OK",
            "version": "8.2",
            "model_count": len(MODELS),
            "models": sorted(MODELS.keys()),
            "narrative": "Typed domain contracts are available for optimizer, decision, planning, and learning layers.",
        }

    @staticmethod
    def schema(model_name: str | None = None) -> dict[str, Any]:
        if model_name:
            model = MODELS.get(model_name)
            if not model:
                return {"status": "NOT_FOUND", "model": model_name, "available": sorted(MODELS.keys())}
            return {"status": "OK", "version": "8.2", "model": model_name, "schema": _schema(model)}

        return {
            "status": "OK",
            "version": "8.2",
            "schemas": {name: _schema(model) for name, model in MODELS.items()},
        }

    @staticmethod
    def sample() -> dict[str, Any]:
        opportunity = Opportunity(
            optimizer_name="BidOptimizer",
            optimizer_version="8.2",
            decision="INCREASE_BID",
            title="Increase bid on proven search term",
            reason="Search term shows profitable conversion history.",
            confidence=82,
            risk="MEDIUM",
            estimated_monthly_impact=125.0,
            score=88.0,
            evidence=[Evidence(source="search_term_report", metric="roas", value=5.2, description="ROAS exceeds target.")],
            impact=ImpactEstimate(estimated_monthly_impact=125.0, currency="USD", basis="recent performance"),
            risk_assessment=RiskAssessment(overall_risk="MEDIUM", factors=["Bid increase may raise spend."]),
        )
        decision = Decision(
            decision="INCREASE_BID",
            priority="MEDIUM",
            confidence=82,
            risk="MEDIUM",
            estimated_monthly_impact=125.0,
            recommended_action="Increase bid by 15%",
            reasoning=["Search term has strong ROAS.", "Risk is controlled by moderate bid increase."],
            payload={"campaign_name": "PET PHOTO - EXACT"},
            optimizer_name="BidOptimizer",
            optimizer_version="8.2",
        )
        plan = Plan(title="Sample Executive Plan", estimated_monthly_impact=125.0, confidence=82.0)
        return {
            "status": "OK",
            "version": "8.2",
            "opportunity": opportunity.to_dict(),
            "decision": decision.to_dict(),
            "plan": plan.to_dict(),
        }
