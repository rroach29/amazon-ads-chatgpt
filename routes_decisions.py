from fastapi import APIRouter, Header

from auth import verify_key
from ai.decision_engine import build_decisions
from marketplace_summary import build_marketplace_summary

router = APIRouter()


@router.get("")
def decisions(
    include_marketplace_summary: bool = True,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)

    result = build_decisions()

    if include_marketplace_summary and isinstance(result, dict):
        result["marketplace_summary"] = build_marketplace_summary()

    return result
