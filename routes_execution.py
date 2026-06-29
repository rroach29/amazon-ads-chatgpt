from fastapi import APIRouter, Header
from pydantic import BaseModel

from auth import verify_key
from execution.engine import (
    approve_decision,
    reject_decision,
    execute_decision,
    execute_approved_decisions,
    approve_and_execute_low_risk_decisions,
)
from execution.log import (
    get_execution_history,
    get_execution_history_for_decision,
)


router = APIRouter()


class RejectDecisionRequest(BaseModel):
    reason: str | None = None


@router.post("/decisions/{decision_id}/approve")
def approve_business_decision(
    decision_id: int,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return approve_decision(decision_id)


@router.post("/decisions/{decision_id}/reject")
def reject_business_decision(
    decision_id: int,
    body: RejectDecisionRequest | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    reason = body.reason if body else None
    return reject_decision(decision_id, reason=reason)


@router.post("/decisions/{decision_id}/execute")
def execute_business_decision(
    decision_id: int,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return execute_decision(decision_id)


@router.post("/decisions/execute-approved")
def execute_all_approved_business_decisions(
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return execute_approved_decisions()


@router.post("/decisions/approve-and-execute-low-risk")
def approve_and_execute_low_risk_business_decisions(
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return approve_and_execute_low_risk_decisions()


@router.get("/execution-history")
def business_os_execution_history(
    limit: int = 100,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return get_execution_history(limit=limit)


@router.get("/decisions/{decision_id}/execution-history")
def business_os_decision_execution_history(
    decision_id: int,
    limit: int = 25,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return get_execution_history_for_decision(decision_id, limit=limit)
