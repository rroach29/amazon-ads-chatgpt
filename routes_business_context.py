from fastapi import APIRouter, Header

from auth import verify_key
from business_context import get_business_os_context

router = APIRouter()


@router.get("/context")
def business_os_context(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return get_business_os_context()
