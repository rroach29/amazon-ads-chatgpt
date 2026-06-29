from fastapi import APIRouter, Header

from auth import verify_key
from ai.intelligence import build_business_intelligence

router = APIRouter()


@router.get("")
def business_intelligence(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return build_business_intelligence()
