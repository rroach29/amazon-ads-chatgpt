from fastapi import APIRouter, Header
from pydantic import BaseModel

from auth import verify_key
from marketplace_profiles import (
    seed_default_us_profile,
    upsert_marketplace_profile,
    list_marketplace_profiles,
    get_marketplace_profile,
    add_canada_profile,
)


router = APIRouter()


class MarketplaceProfileRequest(BaseModel):
    profile_id: str
    country_code: str
    marketplace: str | None = None
    currency: str | None = None
    account_name: str | None = None
    timezone: str | None = None
    active: bool = True


class CanadaProfileRequest(BaseModel):
    profile_id: str


@router.post("/marketplace-profiles/seed-us")
def seed_us_marketplace_profile(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return seed_default_us_profile()


@router.get("/marketplace-profiles")
def get_marketplace_profiles(
    active_only: bool = False,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return list_marketplace_profiles(active_only=active_only)


@router.get("/marketplace-profiles/{country_code}")
def get_marketplace_profile_by_country(
    country_code: str,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return get_marketplace_profile(country_code=country_code)


@router.post("/marketplace-profiles")
def create_or_update_marketplace_profile(
    body: MarketplaceProfileRequest,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)

    return upsert_marketplace_profile(
        profile_id=body.profile_id,
        country_code=body.country_code,
        marketplace=body.marketplace,
        currency=body.currency,
        account_name=body.account_name,
        timezone=body.timezone,
        active=body.active,
    )


@router.post("/marketplace-profiles/canada")
def create_canada_marketplace_profile(
    body: CanadaProfileRequest,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return add_canada_profile(profile_id=body.profile_id)
