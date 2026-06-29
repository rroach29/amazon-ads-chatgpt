from datetime import datetime, timezone
from sqlalchemy import text

from database import SessionLocal
from models import DecisionHistory
from learning.confidence import calculate_accuracy_percent, adjusted_confidence
from learning.metrics import ensure_decision_learning_table

INSERT_LEARNING_SQL = """
INSERT INTO decision_learning (
    decision_history_id,
    decision_type,
    estimated_impact,
    actual_impact,
    accuracy_percent,
    confidence_before,
    confidence_after,
    days_until_measured,
    measured_at,
    notes
)
VALUES (
    :decision_history_id,
    :decision_type,
    :estimated_impact,
    :actual_impact,
    :accuracy_percent,
    :confidence_before,
    :confidence_after,
    :days_until_measured,
    :measured_at,
    :notes
)
RETURNING id;
"""

EXISTS_SQL = """
SELECT id
FROM decision_learning
WHERE decision_history_id = :decision_history_id
LIMIT 1;
"""


def evaluate_decision_learning(
    decision_id,
    actual_impact=None,
    days_until_measured=7,
    notes=None,
):
    db = SessionLocal()

    try:
        ensure_decision_learning_table(db)

        decision = (
            db.query(DecisionHistory)
            .filter(DecisionHistory.id == decision_id)
            .first()
        )

        if not decision:
            return {
                "status": "ERROR",
                "message": f"Decision {decision_id} not found.",
            }

        existing = db.execute(
            text(EXISTS_SQL),
            {"decision_history_id": decision_id},
        ).fetchone()

        if existing:
            return {
                "status": "SKIPPED",
                "message": f"Learning record already exists for decision {decision_id}.",
                "learning_id": existing._mapping["id"],
            }

        estimated = float(decision.estimated_monthly_impact or 0)

        # If actual_impact is not provided, use decision.actual_impact if manually evaluated.
        actual = actual_impact
        if actual is None:
            actual = decision.actual_impact

        if actual is None:
            return {
                "status": "ERROR",
                "message": "actual_impact is required unless decision.actual_impact has already been set.",
            }

        actual = float(actual)
        confidence_before = float(decision.confidence or 0)
        accuracy = calculate_accuracy_percent(estimated, actual)
        confidence_after = adjusted_confidence(confidence_before, accuracy)

        result = db.execute(
            text(INSERT_LEARNING_SQL),
            {
                "decision_history_id": decision.id,
                "decision_type": decision.decision,
                "estimated_impact": estimated,
                "actual_impact": actual,
                "accuracy_percent": accuracy,
                "confidence_before": confidence_before,
                "confidence_after": confidence_after,
                "days_until_measured": days_until_measured,
                "measured_at": datetime.now(timezone.utc),
                "notes": notes,
            },
        )

        learning_id = result.scalar()

        decision.actual_impact = actual
        decision.was_correct = accuracy >= 70
        decision.evaluated_at = datetime.utcnow()
        if notes:
            decision.notes = notes

        db.commit()

        return {
            "status": "OK",
            "learning_id": learning_id,
            "decision_id": decision.id,
            "decision_type": decision.decision,
            "estimated_impact": estimated,
            "actual_impact": actual,
            "accuracy_percent": accuracy,
            "confidence_before": confidence_before,
            "confidence_after": confidence_after,
        }

    except Exception as exc:
        db.rollback()
        return {
            "status": "ERROR",
            "message": "Failed to evaluate decision learning.",
            "error": str(exc),
        }

    finally:
        db.close()


def recalculate_learning_from_evaluated_decisions(limit=100):
    db = SessionLocal()

    try:
        decisions = (
            db.query(DecisionHistory)
            .filter(DecisionHistory.actual_impact.isnot(None))
            .order_by(DecisionHistory.evaluated_at.desc().nullslast())
            .limit(limit)
            .all()
        )
        ids = [decision.id for decision in decisions]

    finally:
        db.close()

    results = []
    for decision_id in ids:
        results.append(evaluate_decision_learning(decision_id))

    return {
        "status": "OK",
        "count": len(results),
        "results": results,
    }
