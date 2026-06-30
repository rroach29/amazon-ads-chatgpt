from datetime import datetime

from database import SessionLocal
from models import DecisionHistory
from business_data_context import resolve_data_context


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


def _payload_dict(value):
    return value if isinstance(value, dict) else {}


def _payload_window(payload):
    payload = _payload_dict(payload)
    window = payload.get("data_window")
    return window if isinstance(window, dict) else {}


def _same_window(existing_payload, new_payload):
    existing_window = _payload_window(existing_payload)
    new_window = _payload_window(new_payload)

    if not existing_window and not new_window:
        return True

    return (
        existing_window.get("start_date") == new_window.get("start_date")
        and existing_window.get("end_date") == new_window.get("end_date")
    )


def _same_identity(existing_payload, new_payload, decision_type):
    existing_payload = _payload_dict(existing_payload)
    new_payload = _payload_dict(new_payload)

    if str(existing_payload.get("campaign_id")) != str(new_payload.get("campaign_id")):
        return False

    # Campaign decisions are unique by decision type + campaign + data window.
    if decision_type in ["PAUSE_CAMPAIGN", "INCREASE_BUDGET", "DECREASE_BUDGET", "SET_BUDGET"]:
        return True

    # Search-term decisions are unique by decision type + campaign + search term + data window.
    if str(existing_payload.get("search_term") or "") == str(new_payload.get("search_term") or ""):
        return True

    # Bid decisions can also be matched on keyword_id.
    if decision_type in ["REDUCE_BID", "SET_BID"]:
        if new_payload.get("keyword_id") and str(existing_payload.get("keyword_id")) == str(new_payload.get("keyword_id")):
            return True

    return False


def _merge_payload(existing_payload, new_payload):
    existing_payload = _payload_dict(existing_payload)
    new_payload = _payload_dict(new_payload)

    merged = dict(existing_payload)
    changed = False

    for key, value in new_payload.items():
        if value not in [None, "", [], {}] and merged.get(key) != value:
            merged[key] = value
            changed = True

    return merged, changed


def save_decisions_to_history(decisions):
    db = SessionLocal()

    try:
        saved = 0
        updated = 0

        for decision in decisions:
            payload = decision.get("payload", {})
            decision_type = decision.get("decision")

            open_items = (
                db.query(DecisionHistory)
                .filter(DecisionHistory.status == "OPEN")
                .filter(DecisionHistory.decision == decision_type)
                .all()
            )

            existing_item = None

            for item in open_items:
                existing_payload = item.payload or {}

                if (
                    _same_identity(existing_payload, payload, decision_type)
                    and _same_window(existing_payload, payload)
                ):
                    existing_item = item
                    break

            if existing_item:
                merged_payload, changed = _merge_payload(existing_item.payload or {}, payload)

                if changed:
                    existing_item.payload = merged_payload
                    existing_item.priority = decision.get("priority", existing_item.priority)
                    existing_item.confidence = decision.get("confidence", existing_item.confidence)
                    existing_item.risk = decision.get("risk", existing_item.risk)
                    existing_item.recommended_action = decision.get("recommended_action", existing_item.recommended_action)
                    existing_item.reasoning = decision.get("reasoning", existing_item.reasoning)
                    existing_item.estimated_monthly_impact = decision.get(
                        "estimated_monthly_impact",
                        existing_item.estimated_monthly_impact,
                    )
                    updated += 1

                continue

            row = DecisionHistory(
                channel="amazon_ads",
                decision=decision_type,
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
            "updated": updated,
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def _is_current_open_decision(row, context):
    payload = _payload_dict(row.payload)
    window = _payload_window(payload)

    # Hide legacy open decisions from default views. They were created before
    # data_window existed and are often based on stale/mixed windows.
    if not window:
        return False

    return (
        window.get("start_date") == context.get("start_date")
        and window.get("end_date") == context.get("end_date")
    )


def get_decision_history(
    status: str = None,
    limit: int = 100,
    current_window_only: bool = True,
    include_legacy: bool = False,
):
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
            .limit(limit * 5)
            .all()
        )

        data_context = None

        if status == "OPEN" and current_window_only:
            data_context = resolve_data_context(window="latest")
            rows = [
                row for row in rows
                if _is_current_open_decision(row, data_context) or include_legacy
            ]

        rows = rows[:limit]

        return {
            "status": "OK",
            "count": len(rows),
            "data_context": data_context,
            "current_window_only": current_window_only if status == "OPEN" else False,
            "include_legacy": include_legacy,
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
