from fastapi import APIRouter, Header

from auth import verify_key
from ai.decision_engine import build_decisions

router = APIRouter()


@router.get("")
def decisions(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return build_decisions()
