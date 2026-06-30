from fastapi import APIRouter, Header
from pydantic import BaseModel

from auth import verify_key
from outcome_intelligence import OutcomeTracker, DecisionAnalytics, OptimizerScorecard

router = APIRouter()


class OutcomeRecordRequest(BaseModel):
    actual_impact: float
    evaluation_period_days: int = 14
    outcome_status: str | None = None
    notes: str | None = None
    raw: dict | None = None


@router.get("/outcomes")
def business_os_outcomes(
    limit: int = 100,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return OutcomeTracker.list_outcomes(limit=limit)


@router.get("/outcomes/{decision_id}")
def business_os_decision_outcomes(
    decision_id: int,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return OutcomeTracker.get_decision_outcomes(decision_id=decision_id)


@router.post("/outcomes/{decision_id}/record")
def business_os_record_outcome(
    decision_id: int,
    body: OutcomeRecordRequest,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return OutcomeTracker.record_outcome(
        decision_id=decision_id,
        actual_impact=body.actual_impact,
        evaluation_period_days=body.evaluation_period_days,
        outcome_status=body.outcome_status,
        notes=body.notes,
        raw=body.raw,
    )


@router.get("/analytics")
def business_os_decision_analytics(
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return DecisionAnalytics.analytics()


@router.get("/optimizer-scorecard")
def business_os_optimizer_scorecard(
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return OptimizerScorecard.scorecard()
