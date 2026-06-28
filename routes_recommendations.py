from fastapi import APIRouter, Header

from auth import verify_key
from recommendations import build_recommendations

router = APIRouter()


@router.get("")
def recommendations(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return build_recommendations()
