from datetime import datetime

from database import SessionLocal
from models import DecisionHistory


def serialize_decision_history(row):
    return {
        "id": row.id,
        "created_at": str(row.created_at),
        "evaluated_at": str(row.evaluated_at) if row.evaluated_at else None,
        "channel": row.channel,
        "decision": row.decision,
        "priority": row.priority,
        "confidence": row.confidence,
        "risk": row.risk,
        "recommended_action": row.recommended_action,
        "reasoning": row.reasoning,
        "payload": row.payload,
        "estimated_monthly_impact": row.estimated_monthly_impact,
        "status": row.status,
        "outcome": row.outcome,
        "actual_impact": row.actual_impact,
        "was_correct": row.was_correct,
        "notes": row.notes,
    }


def save_decisions_to_history(decisions):
    db = SessionLocal()

    try:
        saved = 0

        for decision in decisions:

            payload = decision.get("payload", {})

            open_items = (
                db.query(DecisionHistory)
                .filter(DecisionHistory.status == "OPEN")
                .filter(DecisionHistory.decision == decision.get("decision"))
                .all()
            )

            exists = False

            for item in open_items:
                existing_payload = item.payload or {}

                if (
                    str(existing_payload.get("campaign_id"))
                    == str(payload.get("campaign_id"))
                    and str(existing_payload.get("search_term"))
                    == str(payload.get("search_term"))
                ):
                    exists = True
                    break

            if exists:
                continue

            row = DecisionHistory(
                channel="amazon_ads",
                decision=decision.get("decision"),
                priority=decision.get("priority"),
                confidence=decision.get("confidence"),
                risk=decision.get("risk"),
                recommended_action=decision.get("recommended_action"),
                reasoning=decision.get("reasoning"),
                payload=payload,
                estimated_monthly_impact=decision.get("estimated_monthly_impact", 0),
                status="OPEN",
            )

            db.add(row)
            saved += 1

        db.commit()

        return {
            "status": "OK",
            "saved": saved,
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def get_decision_history(status: str = None, limit: int = 100):
    db = SessionLocal()

    try:
        query = (
            db.query(DecisionHistory)
            .filter(DecisionHistory.channel == "amazon_ads")
        )

        if status:
            query = query.filter(DecisionHistory.status == status)

        rows = (
            query
            .order_by(DecisionHistory.created_at.desc())
            .limit(limit)
            .all()
        )

        return {
            "status": "OK",
            "count": len(rows),
            "items": [serialize_decision_history(row) for row in rows],
        }

    finally:
        db.close()


def evaluate_decision(
    decision_id: int,
    outcome: str,
    actual_impact: float = None,
    was_correct: bool = None,
    notes: str = None,
):
    db = SessionLocal()

    try:
        row = db.query(DecisionHistory).filter(DecisionHistory.id == decision_id).first()

        if not row:
            return {
                "status": "NOT_FOUND",
                "message": "Decision history item not found.",
            }

        row.status = "EVALUATED"
        row.evaluated_at = datetime.utcnow()
        row.outcome = outcome
        row.actual_impact = actual_impact
        row.was_correct = was_correct
        row.notes = notes

        db.commit()

        return {
            "status": "OK",
            "message": "Decision evaluated.",
            "item": serialize_decision_history(row),
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()
