"""Business OS v0.3.0 — Mission Control routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from business_os.mission_control.service import MissionControlService

router = APIRouter()


@router.get("/mission-control/summary")
def mission_control_summary(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return MissionControlService.summary()


@router.post("/mission-control/generate")
def mission_control_generate(
    limit: int = 250,
    replace_pending: bool = True,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return MissionControlService.generate(limit=limit, replace_pending=replace_pending)


@router.get("/mission-control/decisions")
def mission_control_decisions(
    status: str = "Pending",
    limit: int = 100,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return MissionControlService.list_decisions(status=status, limit=limit)


@router.get("/mission-control/decisions/{decision_id}")
def mission_control_get_decision(
    decision_id: str,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return MissionControlService.get_decision(decision_id)


@router.post("/mission-control/decisions/{decision_id}/approve")
def mission_control_approve_decision(
    decision_id: str,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return MissionControlService.approve(decision_id)


@router.post("/mission-control/decisions/{decision_id}/dismiss")
def mission_control_dismiss_decision(
    decision_id: str,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return MissionControlService.dismiss(decision_id)


@router.post("/mission-control/decisions/{decision_id}/defer")
def mission_control_defer_decision(
    decision_id: str,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return MissionControlService.defer(decision_id)


@router.get("/mission-control/decisions/{decision_id}/simulate")
def mission_control_simulate_decision(
    decision_id: str,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return MissionControlService.simulate(decision_id)


@router.get("/mission-control/decisions/{decision_id}/explain")
def mission_control_explain_decision(
    decision_id: str,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return MissionControlService.explain(decision_id)


@router.get("/mission-control/objectives")
def mission_control_objectives(
    master_product_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return MissionControlService.objectives(master_product_id=master_product_id)


@router.post("/mission-control/objectives")
def mission_control_create_objective(
    title: str,
    objective_type: str = "Maximize Profit",
    portfolio_strategy: str = "Grow",
    scope: str = "business",
    master_product_id: str | None = None,
    notes: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return MissionControlService.create_objective(
        title=title,
        objective_type=objective_type,
        portfolio_strategy=portfolio_strategy,
        scope=scope,
        master_product_id=master_product_id,
        notes=notes,
    )
