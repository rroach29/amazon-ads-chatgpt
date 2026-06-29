from fastapi import APIRouter, Header

from auth import verify_key
from decision_history import (
    get_decision_history,
    evaluate_decision,
)

router = APIRouter()


@router.get("")
def decision_history(
    status: str = None,
    limit: int = 100,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return get_decision_history(status, limit)


@router.post("/{decision_id}/evaluate")
def evaluate_history_item(
    decision_id: int,
    outcome: str,
    actual_impact: float = None,
    was_correct: bool = None,
    notes: str = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return evaluate_decision(
        decision_id,
        outcome,
        actual_impact,
        was_correct,
        notes,
    )
