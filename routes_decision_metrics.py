from fastapi import APIRouter, Header

from auth import verify_key
from decision_metrics import get_decision_metrics

router = APIRouter()


@router.get("")
def decision_metrics(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return get_decision_metrics()
