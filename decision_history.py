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


def _payload_identity(payload):
    payload = payload if isinstance(payload, dict) else {}

    return {
        "campaign_id": str(payload.get("campaign_id") or ""),
        "search_term": str(payload.get("search_term") or ""),
        "keyword_id": str(payload.get("keyword_id") or ""),
        "keyword": str(payload.get("keyword") or ""),
        "ad_group_id": str(payload.get("ad_group_id") or ""),
    }


def _merge_payload(existing_payload, new_payload):
    """
    Preserve existing payload values, but fill in any missing/blank values from
    the new decision payload.

    This fixes stale open decisions created before newer execution fields existed,
    for example REDUCE_BID decisions missing keyword_id.
    """
    existing_payload = existing_payload if isinstance(existing_payload, dict) else {}
    new_payload = new_payload if isinstance(new_payload, dict) else {}

    merged = dict(existing_payload)
    changed = False

    for key, value in new_payload.items():
        existing_value = merged.get(key)

        if existing_value in [None, "", [], {}] and value not in [None, "", [], {}]:
            merged[key] = value
            changed = True

    # Also allow the newer decision to refresh marketplace/execution identity fields.
    refreshable_keys = [
        "keyword_id",
        "target_id",
        "campaign_id",
        "ad_group_id",
        "profile_id",
        "country_code",
        "marketplace",
        "currency",
        "suggested_bid_reduction_percent",
        "reduction_percent",
        "suggested_budget_increase_percent",
        "increase_percent",
    ]

    for key in refreshable_keys:
        value = new_payload.get(key)
        if value not in [None, "", [], {}] and merged.get(key) != value:
            merged[key] = value
            changed = True

    return merged, changed


def _same_decision(existing_payload, new_payload, decision_type):
    existing = _payload_identity(existing_payload)
    new = _payload_identity(new_payload)

    if existing["campaign_id"] != new["campaign_id"]:
        return False

    # Search-term decisions are normally unique by campaign + search term.
    if new["search_term"] and existing["search_term"] == new["search_term"]:
        return True

    # Bid decisions should also consider keyword_id if available.
    if decision_type in ["REDUCE_BID", "SET_BID"]:
        if new["keyword_id"] and existing["keyword_id"] == new["keyword_id"]:
            return True

        if (
            new["keyword"]
            and existing["keyword"] == new["keyword"]
            and new["ad_group_id"]
            and existing["ad_group_id"] == new["ad_group_id"]
        ):
            return True

    return False


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

                if _same_decision(existing_payload, payload, decision_type):
                    existing_item = item
                    break

            if existing_item:
                merged_payload, changed = _merge_payload(existing_item.payload or {}, payload)

                if changed:
                    existing_item.payload = merged_payload
                    existing_item.priority = decision.get("priority", existing_item.priority)
                    existing_item.confidence = decision.get("confidence", existing_item.confidence)
                    existing_item.risk = decision.get("risk", existing_item.risk)
                    existing_item.recommended_action = decision.get(
                        "recommended_action",
                        existing_item.recommended_action,
                    )
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
