from fastapi import APIRouter, Header

from auth import verify_key
from ai.intelligence import build_business_intelligence

router = APIRouter()


@router.get("")
def business_intelligence(
    country_code: str | None = None,
    profile_id: str | None = None,
    compare_to: str = "US",
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return build_business_intelligence(
        country_code=country_code,
        profile_id=profile_id,
        compare_to=compare_to,
    )
