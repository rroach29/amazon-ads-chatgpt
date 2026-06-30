"""Business OS v8.3 — Planning Foundation Routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from planning import PlanningFoundation

router = APIRouter()


@router.get("/planning/foundation")
def business_os_planning_foundation(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return PlanningFoundation.describe()


@router.get("/planning/sample")
def business_os_planning_sample(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return PlanningFoundation.sample()
