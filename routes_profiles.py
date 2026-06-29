from fastapi import APIRouter, Header

from auth import verify_key
from amazon_ads import get_profiles


router = APIRouter()


@router.get("")
def get_amazon_ads_profiles(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return get_profiles()
