"""
Business OS v8.0 — Mission Control 2.0 Routes

Swagger-first executive endpoints layered on top of existing Business OS services.
No SQL migration is required for this release.
"""

from fastapi import APIRouter, Header

from auth import verify_key
from executive import BusinessObjectives, ExecutiveBriefingService, ExecutivePriorityEngine

router = APIRouter()


@router.get("/executive/objectives")
def business_os_executive_objectives(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return BusinessObjectives.list()


@router.get("/executive/priorities")
def business_os_executive_priorities(
    objective: str | None = None,
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    max_priorities: int = 10,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ExecutivePriorityEngine.build_priorities(
        objective=objective,
        window=window,
        country_code=country_code,
        profile_id=profile_id,
        max_priorities=max_priorities,
    )


@router.get("/executive/briefing")
def business_os_executive_briefing(
    objective: str | None = None,
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ExecutiveBriefingService.briefing(
        objective=objective,
        window=window,
        country_code=country_code,
        profile_id=profile_id,
    )


@router.get("/executive/what-should-i-do-today")
def business_os_what_should_i_do_today(
    objective: str | None = None,
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ExecutiveBriefingService.what_should_i_do_today(
        objective=objective,
        window=window,
        country_code=country_code,
        profile_id=profile_id,
    )


@router.get("/mission-control/v2")
def business_os_mission_control_v2(
    objective: str | None = None,
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ExecutiveBriefingService.briefing(
        objective=objective,
        window=window,
        country_code=country_code,
        profile_id=profile_id,
    )
