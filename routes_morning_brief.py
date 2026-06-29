from fastapi import APIRouter, Header

from auth import verify_key
from morning_brief import build_morning_brief

router = APIRouter()


@router.get("")
def morning_brief(
    country_code: str | None = None,
    profile_id: str | None = None,
    compare_to: str = "US",
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return build_morning_brief(
        country_code=country_code,
        profile_id=profile_id,
        compare_to=compare_to,
    )
