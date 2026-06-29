from fastapi import APIRouter, Header

from auth import verify_key
from trends import build_trend_summary

router = APIRouter()


@router.get("")
def trends(days: int = 14, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return build_trend_summary(days)
