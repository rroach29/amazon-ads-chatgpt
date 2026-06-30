"""
Business OS v3.6.1
Marketplace-Aware Execution Planner

Builds execution plans from DecisionHistory IDs and enriches campaign actions
with campaign identity:

campaign_id -> profile_id / country_code / marketplace / currency

This makes GPT planning safe and useful before live execution.
"""

from database import SessionLocal
from models import DecisionHistory
from campaign_identity import enrich_payload_with_campaign_identity
from execution_registry import get_action_metadata
from execution_limits import check_batch_limits


def _payload_dict(decision):
    return decision.payload if isinstance(decision.payload, dict) else {}


def _get_campaign_id(payload):
    return payload.get("campaign_id") or payload.get("campaignId")


def _compact_identity(identity_result):
    if not isinstance(identity_result, dict):
        return None

    identity = identity_result.get("identity")
    if not isinstance(identity, dict):
        identity = identity_result

    return {
        "status": identity.get("status"),
        "campaign_id": identity.get("campaign_id"),
        "campaign_name": identity.get("campaign_name"),
        "campaign_status": identity.get("campaign_status"),
        "profile_id": identity.get("profile_id"),
        "country_code": identity.get("country_code"),
        "marketplace": identity.get("marketplace"),
        "currency": identity.get("currency"),
        "date": identity.get("date"),
        "message": identity.get("message"),
    }


def _build_step(index, decision, dry_run=True):
    payload = _payload_dict(decision)
    action = decision.decision
    metadata = get_action_metadata(action)

    identity_result = None
    enriched_payload = dict(payload)
    identity = None

    if metadata.get("requires_campaign_identity"):
        identity_result = enrich_payload_with_campaign_identity(payload=payload)
        identity = _compact_identity(identity_result)

        if identity_result.get("status") == "OK":
            enriched_payload = identity_result.get("payload", payload)

    country_code = enriched_payload.get("country_code")
    marketplace = enriched_payload.get("marketplace")
    profile_id = enriched_payload.get("profile_id")

    supported = bool(metadata.get("supported"))
    live_supported = bool(metadata.get("live_supported"))

    identity_ok = True
    if metadata.get("requires_campaign_identity"):
        identity_ok = identity_result is not None and identity_result.get("status") == "OK"

    ready_for_live_execution = (
        supported
        and live_supported
        and identity_ok
        and profile_id is not None
        and country_code is not None
    )

    blockers = []

    if not supported:
        blockers.append(metadata.get("reason") or "Action is not currently supported.")

    if supported and not live_supported:
        blockers.append("Action is not currently live-supported.")

    if metadata.get("requires_campaign_identity") and not identity_ok:
        blockers.append(
            f"Campaign identity could not be resolved: {(identity or {}).get('message')}"
        )

    if metadata.get("requires_campaign_identity") and not profile_id:
        blockers.append("Missing resolved profile_id.")

    if metadata.get("requires_campaign_identity") and not country_code:
        blockers.append("Missing resolved country_code.")

    return {
        "step": index,
        "decision_id": decision.id,
        "action": action,
        "recommended_action": decision.recommended_action,
        "priority": decision.priority,
        "risk": decision.risk,
        "confidence": decision.confidence,
        "estimated_monthly_impact": decision.estimated_monthly_impact,
        "campaign_id": _get_campaign_id(enriched_payload),
        "campaign_name": enriched_payload.get("campaign_name"),
        "country_code": country_code,
        "marketplace": marketplace,
        "currency": enriched_payload.get("currency"),
        "profile_id": profile_id,
        "profile_id_present": profile_id is not None,
        "identity_resolution": identity,
        "ready_for_live_execution": ready_for_live_execution,
        "blockers": blockers,
        "metadata": metadata,
    }


def build_execution_plan(decision_ids, dry_run=True):
    decision_ids = decision_ids or []
    db = SessionLocal()

    try:
        decisions = (
            db.query(DecisionHistory)
            .filter(DecisionHistory.id.in_(decision_ids))
            .order_by(DecisionHistory.created_at.asc())
            .all()
        )

        found_ids = {decision.id for decision in decisions}
        missing_ids = [
            decision_id for decision_id in decision_ids
            if decision_id not in found_ids
        ]

        steps = [
            _build_step(index + 1, decision, dry_run=dry_run)
            for index, decision in enumerate(decisions)
        ]

        total_impact = round(
            sum(step.get("estimated_monthly_impact") or 0 for step in steps),
            2,
        )

        ready_steps = [
            step for step in steps
            if step.get("ready_for_live_execution")
        ]

        blocked_steps = [
            step for step in steps
            if not step.get("ready_for_live_execution")
        ]

        limit_check = check_batch_limits(steps, dry_run=dry_run)

        return {
            "status": "OK",
            "dry_run": dry_run,
            "decision_count": len(steps),
            "missing_decision_ids": missing_ids,
            "ready_for_live_count": len(ready_steps),
            "blocked_count": len(blocked_steps),
            "total_estimated_monthly_impact": total_impact,
            "limit_check": limit_check,
            "steps": steps,
        }

    finally:
        db.close()
