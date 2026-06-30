"""
Business OS v3.6.0
Execution Planner

Builds an execution plan from DecisionHistory records before anything is queued
or executed.
"""

from database import SessionLocal
from models import DecisionHistory
from execution_registry import get_action_metadata
from execution_limits import evaluate_batch_limits


def _serialize_decision(row):
    payload = row.payload if isinstance(row.payload, dict) else {}
    return {
        "id": row.id,
        "decision": row.decision,
        "priority": row.priority,
        "confidence": row.confidence,
        "risk": row.risk,
        "recommended_action": row.recommended_action,
        "estimated_monthly_impact": row.estimated_monthly_impact,
        "status": row.status,
        "payload": payload,
        "campaign_id": payload.get("campaign_id") or payload.get("campaignId"),
        "campaign_name": payload.get("campaign_name"),
        "profile_id": payload.get("profile_id"),
        "country_code": payload.get("country_code"),
        "marketplace": payload.get("marketplace"),
        "currency": payload.get("currency"),
    }


def load_decisions(decision_ids):
    decision_ids = [int(x) for x in decision_ids]
    db = SessionLocal()
    try:
        rows = (
            db.query(DecisionHistory)
            .filter(DecisionHistory.id.in_(decision_ids))
            .all()
        )
        found = {row.id: _serialize_decision(row) for row in rows}
        ordered = [found[x] for x in decision_ids if x in found]
        missing = [x for x in decision_ids if x not in found]
        return ordered, missing
    finally:
        db.close()


def build_execution_plan(decision_ids, dry_run=True):
    decisions, missing = load_decisions(decision_ids)

    steps = []
    total_estimated_impact = 0

    for index, decision in enumerate(decisions, start=1):
        metadata = get_action_metadata(decision.get("decision"))
        impact = decision.get("estimated_monthly_impact") or 0
        try:
            total_estimated_impact += float(impact)
        except Exception:
            pass

        steps.append({
            "step": index,
            "decision_id": decision.get("id"),
            "action": decision.get("decision"),
            "recommended_action": decision.get("recommended_action"),
            "priority": decision.get("priority"),
            "risk": decision.get("risk"),
            "confidence": decision.get("confidence"),
            "estimated_monthly_impact": decision.get("estimated_monthly_impact"),
            "campaign_id": decision.get("campaign_id"),
            "campaign_name": decision.get("campaign_name"),
            "country_code": decision.get("country_code"),
            "marketplace": decision.get("marketplace"),
            "profile_id_present": bool(decision.get("profile_id")),
            "metadata": metadata,
        })

    limit_result = evaluate_batch_limits(decisions, dry_run=dry_run)

    return {
        "status": "OK" if not missing and limit_result.get("ok") else "REVIEW_REQUIRED",
        "dry_run": dry_run,
        "decision_count": len(decisions),
        "missing_decision_ids": missing,
        "total_estimated_monthly_impact": round(total_estimated_impact, 2),
        "limit_check": limit_result,
        "steps": steps,
    }
