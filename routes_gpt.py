from fastapi import APIRouter, Header

from auth import verify_key
from gpt_responses import (
    get_gpt_dashboard,
    get_gpt_morning_brief,
    get_gpt_business_intelligence,
    get_gpt_root_cause,
    get_gpt_decisions,
    get_gpt_forecast,
)

router = APIRouter()


@router.get("/dashboard")
def gpt_dashboard(
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return get_gpt_dashboard(country_code=country_code, profile_id=profile_id)


@router.get("/morning-brief")
def gpt_morning_brief(
    country_code: str | None = None,
    profile_id: str | None = None,
    compare_to: str = "US",
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return get_gpt_morning_brief(
        country_code=country_code,
        profile_id=profile_id,
        compare_to=compare_to,
    )


@router.get("/intelligence")
def gpt_business_intelligence(
    country_code: str | None = None,
    profile_id: str | None = None,
    compare_to: str = "US",
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return get_gpt_business_intelligence(
        country_code=country_code,
        profile_id=profile_id,
        compare_to=compare_to,
    )


@router.get("/root-cause")
def gpt_root_cause(
    metric: str = "acos",
    days: int = 14,
    country_code: str | None = None,
    compare_to: str = "US",
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return get_gpt_root_cause(
        metric=metric,
        days=days,
        country_code=country_code,
        compare_to=compare_to,
    )


@router.get("/decisions")
def gpt_decisions(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return get_gpt_decisions()


@router.get("/forecast")
def gpt_forecast(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return get_gpt_forecast()
