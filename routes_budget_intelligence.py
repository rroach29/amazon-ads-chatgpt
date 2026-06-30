"""
Business OS v7.1
Budget Intelligence Routes

Swagger-first validation endpoints for the Budget Optimizer.
"""

from fastapi import APIRouter, Header

from auth import verify_key
from business_data_context import resolve_data_context
from optimizers.budget_optimizer import BudgetOptimizer

router = APIRouter()


@router.get("/budget-intelligence")
def budget_intelligence(
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    context = resolve_data_context(window=window, country_code=country_code, profile_id=profile_id)
    result = BudgetOptimizer(context=context).run()
    return {
        "status": result.get("status"),
        "context": context,
        "optimizer": result.get("optimizer"),
        "optimizer_version": result.get("optimizer_version"),
        "opportunity_count": result.get("opportunity_count"),
        "decision_count": result.get("decision_count"),
        "opportunities": result.get("opportunities", []),
        "decisions": result.get("decisions", []),
        "metrics": result.get("metrics", {}),
        "narrative": _narrative(result),
    }


@router.get("/budget-intelligence/summary")
def budget_intelligence_summary(
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    context = resolve_data_context(window=window, country_code=country_code, profile_id=profile_id)
    result = BudgetOptimizer(context=context).run()
    decisions = result.get("decisions", [])
    increase = [d for d in decisions if d.get("decision") == "INCREASE_BUDGET"]
    decrease = [d for d in decisions if d.get("decision") == "DECREASE_BUDGET"]
    total_impact = round(sum(float(d.get("estimated_monthly_impact") or 0) for d in decisions), 2)
    return {
        "status": result.get("status"),
        "context": context,
        "decision_count": len(decisions),
        "increase_budget_count": len(increase),
        "decrease_budget_count": len(decrease),
        "estimated_monthly_impact": total_impact,
        "top_decision": decisions[0] if decisions else None,
        "narrative": _narrative(result),
    }


def _narrative(result):
    decisions = result.get("decisions", []) if isinstance(result, dict) else []
    if not decisions:
        return "No budget intelligence opportunities were detected for the selected data context."
    top = decisions[0]
    return (
        f"Top budget signal is {top.get('decision')} with confidence {top.get('confidence')}% "
        f"and estimated monthly impact {top.get('estimated_monthly_impact')}."
    )
