"""Business OS Platform v1.0 routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from business_os.platform.services.platform_service import PlatformService

router = APIRouter()


@router.get("/platform/status")
def business_os_platform_status(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return PlatformService.status()
