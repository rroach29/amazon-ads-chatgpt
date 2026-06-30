from fastapi import APIRouter, Header

from auth import verify_key
from execution_audit import (
    get_execution_audit,
    get_execution_audit_detail,
    rollback_execution,
)

router = APIRouter()


@router.get("/execution-audit")
def execution_audit(
    limit: int = 50,
    status: str | None = None,
    action: str | None = None,
    live_only: bool = False,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return get_execution_audit(
        limit=limit,
        status=status,
        action=action,
        live_only=live_only,
    )


@router.get("/execution-audit/{execution_job_id}")
def execution_audit_detail(
    execution_job_id: int,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return get_execution_audit_detail(execution_job_id)


@router.post("/executions/{execution_job_id}/rollback")
def rollback_execution_job(
    execution_job_id: int,
    dry_run: bool = True,
    confirm_live: bool = False,
    requested_by: str = "GPT",
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return rollback_execution(
        execution_job_id=execution_job_id,
        dry_run=dry_run,
        confirm_live=confirm_live,
        requested_by=requested_by,
    )
