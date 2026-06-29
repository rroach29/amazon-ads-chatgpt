from fastapi import APIRouter, Header

from auth import verify_key
from ai.root_cause import build_root_cause_analysis

router = APIRouter()


@router.get("")
def root_cause(
    metric: str = "acos",
    days: int = 14,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return build_root_cause_analysis(metric, days)
