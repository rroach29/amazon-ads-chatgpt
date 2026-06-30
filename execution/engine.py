from database import SessionLocal
from models import DecisionHistory
from execution.handlers import EXECUTION_HANDLERS
from execution.log import create_execution_log


SAFE_AUTO_EXECUTE_DECISIONS = {
    "PAUSE_CAMPAIGN",
    "ADD_NEGATIVE_KEYWORD",
    "HARVEST_KEYWORD",
    "REDUCE_BID",
    "INCREASE_BID",
    "INCREASE_BUDGET",
}


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


def execute_decision(decision_id, executed_by="ChatGPT"):
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

        try:
            result = handler(decision)
            execution_status = result.get("status", "UNKNOWN")

            decision.status = "EXECUTED"

            if hasattr(decision, "outcome"):
                decision.outcome = execution_status

            if hasattr(decision, "notes"):
                decision.notes = result.get("message")

            db.commit()

            log_result = create_execution_log(
                decision_id=decision.id,
                decision_type=decision.decision,
                status=execution_status,
                dry_run=result.get("dry_run", True),
                undo_supported=result.get("undo_supported", False),
                undo_action=result.get("undo_action"),
                message=result.get("message"),
                amazon_request=result.get("amazon_request"),
                amazon_response=result.get("amazon_response"),
                execution_result=result,
                executed_by=executed_by,
            )

            return {
                "status": "OK",
                "decision_id": decision_id,
                "decision": decision.decision,
                "execution": result,
                "execution_log": log_result,
            }

        except Exception as exc:
            db.rollback()

            log_result = create_execution_log(
                decision_id=decision.id,
                decision_type=decision.decision,
                status="ERROR",
                dry_run=True,
                message="Execution failed.",
                error=str(exc),
                executed_by=executed_by,
            )

            return {
                "status": "ERROR",
                "decision_id": decision_id,
                "decision": decision.decision,
                "message": "Execution failed.",
                "error": str(exc),
                "execution_log": log_result,
            }

    finally:
        db.close()


def execute_approved_decisions(limit=20, executed_by="ChatGPT"):
    db = SessionLocal()

    try:
        decisions = (
            db.query(DecisionHistory)
            .filter(DecisionHistory.status == "APPROVED")
            .limit(limit)
            .all()
        )

        ids = [decision.id for decision in decisions]

    finally:
        db.close()

    results = []

    for decision_id in ids:
        results.append(execute_decision(decision_id, executed_by=executed_by))

    return {
        "status": "OK",
        "count": len(results),
        "results": results,
    }


def approve_and_execute_low_risk_decisions(limit=10, executed_by="ChatGPT"):
    db = SessionLocal()

    try:
        decisions = (
            db.query(DecisionHistory)
            .filter(DecisionHistory.status == "OPEN")
            .filter(DecisionHistory.risk == "LOW")
            .limit(limit)
            .all()
        )

        ids = [decision.id for decision in decisions if decision.decision in SAFE_AUTO_EXECUTE_DECISIONS]

    finally:
        db.close()

    results = []

    for decision_id in ids:
        approve_decision(decision_id)
        results.append(execute_decision(decision_id, executed_by=executed_by))

    return {
        "status": "OK",
        "message": "Approved and executed low-risk decisions.",
        "count": len(results),
        "results": results,
    }
