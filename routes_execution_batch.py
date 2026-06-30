from fastapi import APIRouter, Header
from pydantic import BaseModel

from auth import verify_key
from execution_registry import list_actions
from execution_limits import get_execution_limits
from execution_planner import build_execution_plan
from execution_batch import execute_decision_batch, get_execution_queue

router = APIRouter()


class ExecutionPlanRequest(BaseModel):
    decision_ids: list[int]
    dry_run: bool = True


class ExecutionBatchRequest(BaseModel):
    decision_ids: list[int]
    approved: bool = True
    dry_run: bool = True
    confirm_live: bool = False
    requested_by: str = "GPT"
    stop_on_error: bool = True


@router.get("/execution-actions")
def execution_actions(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return list_actions()


@router.get("/execution-limits")
def execution_limits(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return get_execution_limits()


@router.post("/execution-plan")
def execution_plan(
    body: ExecutionPlanRequest,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return build_execution_plan(
        decision_ids=body.decision_ids,
        dry_run=body.dry_run,
    )


@router.post("/execution-batch")
def execution_batch(
    body: ExecutionBatchRequest,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return execute_decision_batch(
        decision_ids=body.decision_ids,
        approved=body.approved,
        dry_run=body.dry_run,
        confirm_live=body.confirm_live,
        requested_by=body.requested_by,
        stop_on_error=body.stop_on_error,
    )


@router.get("/execution-queue")
def execution_queue(
    status: str = "APPROVED",
    limit: int = 50,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return get_execution_queue(status=status, limit=limit)
