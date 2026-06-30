"""Business OS v8.1 Diagnostics Routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from diagnostics import BusinessOSDiagnostics

router = APIRouter()


@router.get("/diagnostics")
def business_os_diagnostics(
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return BusinessOSDiagnostics.run(country_code=country_code, profile_id=profile_id)
