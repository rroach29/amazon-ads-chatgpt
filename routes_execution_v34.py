from fastapi import APIRouter, Header

from auth import verify_key
from execution_engine import (
    create_execution_job,
    list_execution_jobs,
    get_execution_job,
    cancel_execution_job,
)

router = APIRouter()


@router.post("/execute")
def execute_decision(
    decision_id: int,
    approved: bool = True,
    dry_run: bool = True,
    confirm_live: bool = False,
    requested_by: str = "GPT",
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return create_execution_job(
        decision_id=decision_id,
        approved=approved,
        dry_run=dry_run,
        requested_by=requested_by,
        confirm_live=confirm_live,
    )


@router.get("/executions")
def executions(
    status: str | None = None,
    limit: int = 50,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return list_execution_jobs(status=status, limit=limit)


@router.get("/executions/{execution_job_id}")
def execution_detail(
    execution_job_id: int,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return get_execution_job(execution_job_id)


@router.post("/executions/{execution_job_id}/cancel")
def cancel_execution(
    execution_job_id: int,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return cancel_execution_job(execution_job_id)
