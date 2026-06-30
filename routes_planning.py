"""Business OS v8.4 — Executive Planning Routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from planning.engine import ExecutivePlanningEngine

router = APIRouter()


@router.get("/planning/plan")
def business_os_executive_plan(
    objective: str | None = None,
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    max_actions: int = 20,
    max_initiatives: int = 8,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ExecutivePlanningEngine.build_plan(
        objective=objective,
        window=window,
        country_code=country_code,
        profile_id=profile_id,
        max_actions=max_actions,
        max_initiatives=max_initiatives,
    )


@router.get("/planning/initiatives")
def business_os_executive_initiatives(
    objective: str | None = None,
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    max_actions: int = 20,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ExecutivePlanningEngine.initiatives(
        objective=objective,
        window=window,
        country_code=country_code,
        profile_id=profile_id,
        max_actions=max_actions,
    )


@router.get("/planning/conflicts")
def business_os_planning_conflicts(
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ExecutivePlanningEngine.conflicts(
        window=window,
        country_code=country_code,
        profile_id=profile_id,
    )
