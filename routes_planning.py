"""Business OS v8.4.1 — Planning Foundation and Executive Planning Routes.

Keeps the v8.3 planning foundation endpoints while exposing the v8.4 executive
planning engine. This prevents planning-foundation regressions when replacing
routes_planning.py during v8.4 installation.
"""

from fastapi import APIRouter, Header

from auth import verify_key
from planning import PlanningFoundation
from planning.engine import ExecutivePlanningEngine

router = APIRouter()


@router.get("/planning/foundation")
def business_os_planning_foundation(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return PlanningFoundation.describe()


@router.get("/planning/sample")
def business_os_planning_sample(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return PlanningFoundation.sample()


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


@router.get("/planning/executive-plan")
def business_os_executive_plan_alias(
    objective: str | None = None,
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    max_actions: int = 20,
    max_initiatives: int = 8,
    x_api_key: str = Header(...),
):
    """Alias used by the v8.4 Swagger regression checklist."""
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
