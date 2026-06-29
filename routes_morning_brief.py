from fastapi import APIRouter, Header

from auth import verify_key
from morning_brief import build_morning_brief

router = APIRouter()


@router.get("")
def morning_brief(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return build_morning_brief()
