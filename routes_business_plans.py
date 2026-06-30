from fastapi import APIRouter, Header

from auth import verify_key
from business_plan_engine import (
    build_business_plan,
    simulate_business_plan,
    get_plan_summary,
)

router = APIRouter()


@router.get("/plans/current")
def current_business_plan(
    objective: str | None = None,
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    max_actions: int = 20,
    min_confidence: int = 70,
    include_high_risk: bool = False,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)

    return build_business_plan(
        objective=objective,
        window=window,
        country_code=country_code,
        profile_id=profile_id,
        max_actions=max_actions,
        min_confidence=min_confidence,
        include_high_risk=include_high_risk,
    )


@router.get("/plans/current/summary")
def current_business_plan_summary(
    objective: str | None = None,
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    max_actions: int = 20,
    min_confidence: int = 70,
    include_high_risk: bool = False,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)

    plan = build_business_plan(
        objective=objective,
        window=window,
        country_code=country_code,
        profile_id=profile_id,
        max_actions=max_actions,
        min_confidence=min_confidence,
        include_high_risk=include_high_risk,
    )

    return get_plan_summary(plan)


@router.get("/plans/current/simulation")
def current_business_plan_simulation(
    objective: str | None = None,
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    max_actions: int = 20,
    min_confidence: int = 70,
    include_high_risk: bool = False,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)

    plan = build_business_plan(
        objective=objective,
        window=window,
        country_code=country_code,
        profile_id=profile_id,
        max_actions=max_actions,
        min_confidence=min_confidence,
        include_high_risk=include_high_risk,
    )

    return {
        "status": "OK",
        "plan_summary": get_plan_summary(plan),
        "simulation": simulate_business_plan(plan),
    }
