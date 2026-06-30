from fastapi import APIRouter, Header
from pydantic import BaseModel

from auth import verify_key
from learning.metrics import get_learning_records, get_learning_summary
from learning.evaluator import (
    evaluate_decision_learning,
    recalculate_learning_from_evaluated_decisions,
)
from learning.summary import build_learning_intelligence
from outcome_intelligence import LearningEngine

router = APIRouter()


class LearningEvaluationRequest(BaseModel):
    actual_impact: float | None = None
    days_until_measured: int = 7
    notes: str | None = None


@router.get("")
def business_os_learning(
    limit: int = 100,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return get_learning_records(limit=limit)


@router.get("/summary")
def business_os_learning_summary(
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return get_learning_summary()


@router.get("/intelligence")
def business_os_learning_intelligence(
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return build_learning_intelligence()


@router.get("/feedback")
def business_os_learning_feedback(
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return LearningEngine.feedback_summary()


@router.get("/events")
def business_os_learning_events(
    limit: int = 100,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return LearningEngine.learning_events(limit=limit)


@router.get("/confidence-history")
def business_os_confidence_history(
    limit: int = 100,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return LearningEngine.confidence_history(limit=limit)


@router.get("/confidence-adjustment/{decision_type}")
def business_os_confidence_adjustment(
    decision_type: str,
    optimizer_name: str | None = None,
    default_confidence: float = 70,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return LearningEngine.confidence_adjustment_for(
        decision_type=decision_type,
        optimizer_name=optimizer_name,
        default_confidence=default_confidence,
    )


@router.post("/decisions/{decision_id}/evaluate")
def evaluate_business_os_learning(
    decision_id: int,
    body: LearningEvaluationRequest,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return evaluate_decision_learning(
        decision_id=decision_id,
        actual_impact=body.actual_impact,
        days_until_measured=body.days_until_measured,
        notes=body.notes,
    )


@router.post("/recalculate")
def recalculate_business_os_learning(
    limit: int = 100,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return recalculate_learning_from_evaluated_decisions(limit=limit)
