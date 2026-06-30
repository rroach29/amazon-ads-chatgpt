from fastapi import APIRouter, Header

from auth import verify_key
from campaign_identity import resolve_campaign_identity

router = APIRouter()


@router.get("/campaign-identity/{campaign_id}")
def campaign_identity(
    campaign_id: str,
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return resolve_campaign_identity(
        campaign_id=campaign_id,
        country_code=country_code,
        profile_id=profile_id,
    )
