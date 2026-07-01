"""Business OS v0.5.0 — Execution Framework routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from business_os.execution_framework.planner import ExecutionPlannerService

router = APIRouter()


@router.get("/execution/plans")
def execution_plans(
    status: str | None = None,
    limit: int = 100,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ExecutionPlannerService.list_plans(status=status, limit=limit)


@router.get("/execution/plans/{plan_id}")
def execution_plan_detail(
    plan_id: str,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ExecutionPlannerService.get_plan(plan_id)


@router.post("/execution/simulate/{decision_id}")
def execution_simulate_decision(
    decision_id: str,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ExecutionPlannerService.simulate_decision(decision_id)


@router.post("/execution/approve/{decision_id}")
def execution_approve_decision(
    decision_id: str,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ExecutionPlannerService.create_plan_from_decision(decision_id)


@router.post("/execution/run/{plan_id}")
def execution_run_plan(
    plan_id: str,
    execute_live: bool = False,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ExecutionPlannerService.run_plan(plan_id=plan_id, execute_live=execute_live)


@router.get("/execution/history")
def execution_history(
    limit: int = 100,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ExecutionPlannerService.history(limit=limit)
