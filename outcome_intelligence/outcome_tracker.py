"""
Business OS v6.3
Outcome Tracker

Records and retrieves measured outcomes for executed decisions.
"""

from datetime import datetime, timezone
from sqlalchemy import text

from database import SessionLocal
from models import DecisionHistory
from outcome_intelligence.storage import ensure_outcome_tables
from learning.confidence import calculate_accuracy_percent, adjusted_confidence


INSERT_OUTCOME_SQL = """
INSERT INTO decision_outcomes (
    decision_history_id,
    decision_type,
    optimizer_name,
    estimated_impact,
    actual_impact,
    variance,
    variance_percent,
    outcome_status,
    evaluation_period_days,
    measured_at,
    notes,
    raw
)
VALUES (
    :decision_history_id,
    :decision_type,
    :optimizer_name,
    :estimated_impact,
    :actual_impact,
    :variance,
    :variance_percent,
    :outcome_status,
    :evaluation_period_days,
    :measured_at,
    :notes,
    CAST(:raw AS JSONB)
)
RETURNING id;
"""

SELECT_OUTCOMES_SQL = """
SELECT *
FROM decision_outcomes
ORDER BY measured_at DESC
LIMIT :limit;
"""

SELECT_OUTCOME_FOR_DECISION_SQL = """
SELECT *
FROM decision_outcomes
WHERE decision_history_id = :decision_history_id
ORDER BY measured_at DESC;
"""

INSERT_LEARNING_EVENT_SQL = """
INSERT INTO learning_events (
    event_type,
    decision_history_id,
    decision_type,
    optimizer_name,
    confidence_before,
    confidence_after,
    accuracy_percent,
    message,
    payload
)
VALUES (
    :event_type,
    :decision_history_id,
    :decision_type,
    :optimizer_name,
    :confidence_before,
    :confidence_after,
    :accuracy_percent,
    :message,
    CAST(:payload AS JSONB)
);
"""

INSERT_CONFIDENCE_HISTORY_SQL = """
INSERT INTO confidence_history (
    decision_type,
    optimizer_name,
    confidence_before,
    confidence_after,
    accuracy_percent,
    sample_size
)
VALUES (
    :decision_type,
    :optimizer_name,
    :confidence_before,
    :confidence_after,
    :accuracy_percent,
    :sample_size
);
"""


def _row_to_dict(row):
    data = dict(row._mapping)
    for key in ("measured_at", "created_at", "calculated_at"):
        if data.get(key):
            data[key] = data[key].isoformat()
    return data


def _safe_float(value, default=0.0):
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


class OutcomeTracker:
    @staticmethod
    def record_outcome(
        decision_id,
        actual_impact,
        evaluation_period_days=14,
        outcome_status=None,
        notes=None,
        raw=None,
    ):
        db = SessionLocal()
        try:
            ensure_outcome_tables(db)

            decision = db.query(DecisionHistory).filter(DecisionHistory.id == decision_id).first()
            if not decision:
                return {"status": "ERROR", "message": f"Decision {decision_id} not found."}

            estimated = _safe_float(decision.estimated_monthly_impact)
            actual = _safe_float(actual_impact)
            variance = round(actual - estimated, 2)
            variance_percent = round((variance / estimated) * 100, 2) if estimated else None
            accuracy = calculate_accuracy_percent(estimated, actual)
            confidence_before = _safe_float(decision.confidence)
            confidence_after = adjusted_confidence(confidence_before, accuracy)

            if outcome_status is None:
                if accuracy >= 70:
                    outcome_status = "SUCCESS"
                elif actual > 0:
                    outcome_status = "PARTIAL"
                else:
                    outcome_status = "FAILED"

            payload = raw or {}
            optimizer_name = None
            if isinstance(decision.payload, dict):
                optimizer_name = decision.payload.get("optimizer") or decision.payload.get("source_optimizer")
            optimizer_name = optimizer_name or "unknown"

            result = db.execute(
                text(INSERT_OUTCOME_SQL),
                {
                    "decision_history_id": decision.id,
                    "decision_type": decision.decision,
                    "optimizer_name": optimizer_name,
                    "estimated_impact": estimated,
                    "actual_impact": actual,
                    "variance": variance,
                    "variance_percent": variance_percent,
                    "outcome_status": outcome_status,
                    "evaluation_period_days": evaluation_period_days,
                    "measured_at": datetime.now(timezone.utc),
                    "notes": notes,
                    "raw": __import__("json").dumps(payload),
                },
            )
            outcome_id = result.scalar()

            decision.actual_impact = actual
            decision.was_correct = accuracy >= 70
            decision.outcome = outcome_status
            decision.evaluated_at = datetime.utcnow()
            if notes:
                decision.notes = notes

            event_payload = {
                "outcome_id": outcome_id,
                "estimated_impact": estimated,
                "actual_impact": actual,
                "variance": variance,
                "variance_percent": variance_percent,
            }

            db.execute(
                text(INSERT_LEARNING_EVENT_SQL),
                {
                    "event_type": "OUTCOME_RECORDED",
                    "decision_history_id": decision.id,
                    "decision_type": decision.decision,
                    "optimizer_name": optimizer_name,
                    "confidence_before": confidence_before,
                    "confidence_after": confidence_after,
                    "accuracy_percent": accuracy,
                    "message": f"Outcome recorded for {decision.decision}: {accuracy:.1f}% estimate accuracy.",
                    "payload": __import__("json").dumps(event_payload),
                },
            )

            db.execute(
                text(INSERT_CONFIDENCE_HISTORY_SQL),
                {
                    "decision_type": decision.decision,
                    "optimizer_name": optimizer_name,
                    "confidence_before": confidence_before,
                    "confidence_after": confidence_after,
                    "accuracy_percent": accuracy,
                    "sample_size": 1,
                },
            )

            db.commit()

            return {
                "status": "OK",
                "outcome_id": outcome_id,
                "decision_id": decision.id,
                "decision_type": decision.decision,
                "optimizer_name": optimizer_name,
                "estimated_impact": estimated,
                "actual_impact": actual,
                "variance": variance,
                "variance_percent": variance_percent,
                "accuracy_percent": accuracy,
                "confidence_before": confidence_before,
                "confidence_after": confidence_after,
                "outcome_status": outcome_status,
            }

        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "message": "Failed to record outcome.", "error": str(exc)}
        finally:
            db.close()

    @staticmethod
    def list_outcomes(limit=100):
        db = SessionLocal()
        try:
            ensure_outcome_tables(db)
            rows = db.execute(text(SELECT_OUTCOMES_SQL), {"limit": limit}).fetchall()
            return {"status": "OK", "count": len(rows), "items": [_row_to_dict(row) for row in rows]}
        finally:
            db.close()

    @staticmethod
    def get_decision_outcomes(decision_id):
        db = SessionLocal()
        try:
            ensure_outcome_tables(db)
            rows = db.execute(text(SELECT_OUTCOME_FOR_DECISION_SQL), {"decision_history_id": decision_id}).fetchall()
            return {"status": "OK", "decision_id": decision_id, "count": len(rows), "items": [_row_to_dict(row) for row in rows]}
        finally:
            db.close()
