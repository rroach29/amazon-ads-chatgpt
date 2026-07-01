"""Business OS ChangeSet routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from business_os.change_sets.service import ChangeSetService

router = APIRouter()


@router.get("/change-sets/decision/{decision_id}")
def change_set_for_decision(decision_id: str, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return ChangeSetService.for_decision(decision_id)
