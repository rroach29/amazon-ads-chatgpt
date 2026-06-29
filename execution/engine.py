from database import SessionLocal
from models import DecisionHistory
from execution.handlers import EXECUTION_HANDLERS


def get_decision_or_error(db, decision_id):
    decision = (
        db.query(DecisionHistory)
        .filter(DecisionHistory.id == decision_id)
        .first()
    )

    if not decision:
        return None, {
            "status": "ERROR",
            "message": f"Decision {decision_id} not found.",
        }

    return decision, None


def approve_decision(decision_id):
    db = SessionLocal()

    try:
        decision, error = get_decision_or_error(db, decision_id)

        if error:
            return error

        decision.status = "APPROVED"
        db.commit()

        return {
            "status": "OK",
            "message": f"Decision {decision_id} approved.",
            "decision_id": decision_id,
            "decision": decision.decision,
        }

    finally:
        db.close()


def reject_decision(decision_id, reason=None):
    db = SessionLocal()

    try:
        decision, error = get_decision_or_error(db, decision_id)

        if error:
            return error

        decision.status = "REJECTED"

        if hasattr(decision, "notes"):
            decision.notes = reason

        db.commit()

        return {
            "status": "OK",
            "message": f"Decision {decision_id} rejected.",
            "decision_id": decision_id,
            "decision": decision.decision,
            "reason": reason,
        }

    finally:
        db.close()


def execute_decision(decision_id):
    db = SessionLocal()

    try:
        decision, error = get_decision_or_error(db, decision_id)

        if error:
            return error

        if decision.status != "APPROVED":
            return {
                "status": "ERROR",
                "message": (
                    f"Decision {decision_id} must be APPROVED before execution."
                ),
                "current_status": decision.status,
            }

        handler = EXECUTION_HANDLERS.get(decision.decision)

        if not handler:
            return {
                "status": "ERROR",
                "message": f"No execution handler for {decision.decision}.",
            }

        result = handler(decision)

        decision.status = "EXECUTED"

        if hasattr(decision, "outcome"):
            decision.outcome = result.get("status")

        if hasattr(decision, "notes"):
            decision.notes = result.get("message")

        db.commit()

        return {
            "status": "OK",
            "decision_id": decision_id,
            "decision": decision.decision,
            "execution": result,
        }

    finally:
        db.close()


def execute_approved_decisions(limit=20):
    db = SessionLocal()

    try:
        decisions = (
            db.query(DecisionHistory)
            .filter(DecisionHistory.status == "APPROVED")
            .limit(limit)
            .all()
        )

        decision_ids = [decision.id for decision in decisions]

    finally:
        db.close()

    results = []

    for decision_id in decision_ids:
        results.append(execute_decision(decision_id))

    return {
        "status": "OK",
        "count": len(results),
        "results": results,
    }
