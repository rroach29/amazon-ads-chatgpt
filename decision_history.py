"""
Business OS v6.1.1
Decision Management

Purpose:
- Persist generated optimizer decisions immediately.
- Return stable decision_id values back to /business-os/decisions.
- Preserve the existing DecisionHistory table and routes.
- Avoid a database migration for this patch.

Lifecycle used by the current table:
OPEN -> APPROVED -> EXECUTED
OPEN -> REJECTED
OPEN/APPROVED/EXECUTED -> EVALUATED

Future migration note:
A separate immutable decision_uuid column can be added later. For now, the
existing integer DecisionHistory.id is the stable decision identity used by
Swagger, approval, execution, history, and learning.
"""

from datetime import datetime

from database import SessionLocal
from models import DecisionHistory
from business_data_context import resolve_data_context


OPEN_STATUSES = {"OPEN", "APPROVED"}
CAMPAIGN_DECISIONS = {
    "PAUSE_CAMPAIGN",
    "RESUME_CAMPAIGN",
    "INCREASE_BUDGET",
    "DECREASE_BUDGET",
    "SET_BUDGET",
}
BID_DECISIONS = {"REDUCE_BID", "INCREASE_BID", "SET_BID"}
SEARCH_TERM_DECISIONS = {
    "ADD_NEGATIVE_KEYWORD",
    "HARVEST_KEYWORD",
    "PROMOTE_TO_EXACT",
}


def serialize_decision_history(row):
    return {
        "id": row.id,
        "decision_id": row.id,
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
        "lifecycle": {
            "state": row.status,
            "created_at": str(row.created_at),
            "evaluated_at": str(row.evaluated_at) if row.evaluated_at else None,
            "next_allowed_actions": _next_allowed_actions(row.status),
        },
        "outcome": row.outcome,
        "actual_impact": row.actual_impact,
        "was_correct": row.was_correct,
        "notes": row.notes,
    }


def _next_allowed_actions(status):
    status = str(status or "OPEN").upper()

    if status == "OPEN":
        return ["approve", "reject", "execute_dry_run", "evaluate"]

    if status == "APPROVED":
        return ["execute", "reject", "evaluate"]

    if status == "EXECUTED":
        return ["evaluate", "review_execution_history"]

    if status == "REJECTED":
        return ["evaluate"]

    if status == "EVALUATED":
        return ["review"]

    return ["review"]


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


def _same_campaign(existing_payload, new_payload):
    existing_payload = _payload_dict(existing_payload)
    new_payload = _payload_dict(new_payload)
    return str(existing_payload.get("campaign_id") or "") == str(new_payload.get("campaign_id") or "")


def _same_ad_group(existing_payload, new_payload):
    existing_payload = _payload_dict(existing_payload)
    new_payload = _payload_dict(new_payload)
    existing_ad_group = existing_payload.get("ad_group_id")
    new_ad_group = new_payload.get("ad_group_id")

    if not existing_ad_group and not new_ad_group:
        return True

    return str(existing_ad_group or "") == str(new_ad_group or "")


def _same_identity(existing_payload, new_payload, decision_type):
    existing_payload = _payload_dict(existing_payload)
    new_payload = _payload_dict(new_payload)

    if not _same_campaign(existing_payload, new_payload):
        return False

    # Campaign decisions are unique by decision type + campaign + data window.
    if decision_type in CAMPAIGN_DECISIONS:
        return True

    # Bid decisions are unique by decision type + campaign + keyword/target + data window.
    if decision_type in BID_DECISIONS:
        existing_keyword_id = existing_payload.get("keyword_id") or existing_payload.get("target_id")
        new_keyword_id = new_payload.get("keyword_id") or new_payload.get("target_id")

        if new_keyword_id and str(existing_keyword_id or "") == str(new_keyword_id):
            return True

        # Some targeting rows only have keyword text/target expression.
        return (
            str(existing_payload.get("keyword") or "") == str(new_payload.get("keyword") or "")
            and _same_ad_group(existing_payload, new_payload)
        )

    # Search-term decisions are unique by type + campaign + ad group + search term + data window.
    if decision_type in SEARCH_TERM_DECISIONS:
        return (
            str(existing_payload.get("search_term") or "") == str(new_payload.get("search_term") or "")
            and _same_ad_group(existing_payload, new_payload)
        )

    # Safe fallback: campaign + search term when present.
    if new_payload.get("search_term"):
        return str(existing_payload.get("search_term") or "") == str(new_payload.get("search_term") or "")

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


def _attach_history_identity(decision, row):
    """Return a decision dict enriched with its persistent DecisionHistory identity."""
    enriched = dict(decision or {})
    enriched["id"] = row.id
    enriched["decision_id"] = row.id
    enriched["status"] = row.status
    enriched["created_at"] = str(row.created_at)
    enriched["lifecycle"] = {
        "state": row.status,
        "created_at": str(row.created_at),
        "evaluated_at": str(row.evaluated_at) if row.evaluated_at else None,
        "next_allowed_actions": _next_allowed_actions(row.status),
    }
    return enriched


def save_decisions_to_history(decisions):
    """
    Upsert generated decisions into DecisionHistory and return stable IDs.

    This function intentionally matches current OPEN/APPROVED rows instead of
    creating duplicate decisions every time /business-os/decisions is called.
    """
    db = SessionLocal()

    try:
        saved = 0
        updated = 0
        unchanged = 0
        persisted_items = []

        for decision in decisions:
            payload = decision.get("payload", {})
            decision_type = decision.get("decision")

            open_items = (
                db.query(DecisionHistory)
                .filter(DecisionHistory.status.in_(list(OPEN_STATUSES)))
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
                else:
                    unchanged += 1

                db.flush()
                persisted_items.append(_attach_history_identity(decision, existing_item))
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
            db.flush()
            saved += 1
            persisted_items.append(_attach_history_identity(decision, row))

        db.commit()

        return {
            "status": "OK",
            "saved": saved,
            "updated": updated,
            "unchanged": unchanged,
            "items": persisted_items,
            "ids": [item.get("decision_id") for item in persisted_items],
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


def get_decision(decision_id: int):
    db = SessionLocal()

    try:
        row = db.query(DecisionHistory).filter(DecisionHistory.id == decision_id).first()

        if not row:
            return {
                "status": "NOT_FOUND",
                "message": "Decision not found.",
                "decision_id": decision_id,
            }

        return {
            "status": "OK",
            "item": serialize_decision_history(row),
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
