"""
Business OS v3.7.0
Execution Audit + Budget Rollback

Adds budget rollback support when an execution result contains:
- current_budget
- new_budget

Supported rollback actions:
- PAUSE_CAMPAIGN  -> RESUME_CAMPAIGN
- RESUME_CAMPAIGN -> PAUSE_CAMPAIGN
- SET_BUDGET / INCREASE_BUDGET / DECREASE_BUDGET -> SET_BUDGET back to previous budget
"""

from datetime import datetime

from database import SessionLocal
from execution_models import ExecutionJob, ExecutionResult
from execution_engine import run_execution_job, serialize_execution_job, serialize_execution_result


ROLLBACK_ACTIONS = {
    "PAUSE_CAMPAIGN": "RESUME_CAMPAIGN",
    "RESUME_CAMPAIGN": "PAUSE_CAMPAIGN",
    "SET_BUDGET": "SET_BUDGET",
    "INCREASE_BUDGET": "SET_BUDGET",
    "DECREASE_BUDGET": "SET_BUDGET",
}


def _safe_get(data, *keys, default=None):
    current = data

    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)

    return current if current is not None else default


def _compact_payload(payload):
    payload = payload if isinstance(payload, dict) else {}
    decision_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}

    return {
        "decision_id": payload.get("decision_id"),
        "decision": payload.get("decision"),
        "recommended_action": payload.get("recommended_action"),
        "campaign_id": decision_payload.get("campaign_id") or decision_payload.get("campaignId"),
        "campaign_name": decision_payload.get("campaign_name"),
        "profile_id": decision_payload.get("profile_id"),
        "country_code": decision_payload.get("country_code"),
        "marketplace": decision_payload.get("marketplace"),
        "currency": decision_payload.get("currency"),
        "spend": decision_payload.get("spend"),
        "sales": decision_payload.get("sales"),
        "orders": decision_payload.get("orders"),
        "acos": decision_payload.get("acos"),
        "roas": decision_payload.get("roas"),
    }


def _summarize_amazon_result(result):
    response_json = result.response_json if isinstance(result.response_json, dict) else {}

    amazon_response = response_json.get("response_json")
    if not isinstance(amazon_response, dict):
        amazon_response = response_json

    campaign_response = None

    campaigns = amazon_response.get("campaigns")
    if isinstance(campaigns, list) and campaigns:
        campaign_response = campaigns[0]

    errors = amazon_response.get("errors")
    if errors is None:
        errors = response_json.get("errors")

    return {
        "success": result.success,
        "dry_run": result.dry_run,
        "http_status": result.http_status,
        "amazon_request_id": result.amazon_request_id,
        "action": result.action,
        "status": result.status,
        "campaign_response": campaign_response,
        "errors": errors,
        "error_message": result.error_message,
        "execution_time_ms": result.execution_time_ms,
        "current_budget": response_json.get("current_budget"),
        "new_budget": response_json.get("new_budget"),
        "budget_change": response_json.get("budget_change"),
        "budget_change_percent": response_json.get("budget_change_percent"),
        "budget_validation": response_json.get("budget_validation"),
        "created_at": result.created_at.isoformat() if result.created_at else None,
    }


def _latest_result_for_job(db, job_id):
    return (
        db.query(ExecutionResult)
        .filter(ExecutionResult.execution_job_id == job_id)
        .order_by(ExecutionResult.created_at.desc())
        .first()
    )


def _rollback_available(job, latest_result=None):
    if not job or job.status != "COMPLETED" or job.dry_run:
        return False

    if job.action in ["PAUSE_CAMPAIGN", "RESUME_CAMPAIGN"]:
        return True

    if job.action in ["SET_BUDGET", "INCREASE_BUDGET", "DECREASE_BUDGET"]:
        response_json = latest_result.response_json if latest_result and isinstance(latest_result.response_json, dict) else {}
        return response_json.get("current_budget") is not None

    return False


def get_execution_audit(limit=50, status=None, action=None, live_only=False):
    db = SessionLocal()

    try:
        query = db.query(ExecutionJob).order_by(ExecutionJob.created_at.desc())

        if status:
            query = query.filter(ExecutionJob.status == status)

        if action:
            query = query.filter(ExecutionJob.action == action)

        if live_only:
            query = query.filter(ExecutionJob.dry_run == False)  # noqa: E712

        jobs = query.limit(limit).all()
        items = []

        for job in jobs:
            latest_result = _latest_result_for_job(db, job.id)

            items.append({
                "execution_job_id": job.id,
                "decision_id": job.decision_id,
                "action": job.action,
                "status": job.status,
                "dry_run": job.dry_run,
                "profile_id": job.profile_id,
                "country_code": job.country_code,
                "marketplace": job.marketplace,
                "currency": job.currency,
                "requested_by": job.requested_by,
                "requested_at": job.requested_at.isoformat() if job.requested_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "payload": _compact_payload(job.payload),
                "latest_result": _summarize_amazon_result(latest_result) if latest_result else None,
                "rollback_available": _rollback_available(job, latest_result),
                "rollback_action": ROLLBACK_ACTIONS.get(job.action),
            })

        return {
            "status": "OK",
            "count": len(items),
            "items": items,
        }

    finally:
        db.close()


def get_execution_audit_detail(execution_job_id):
    db = SessionLocal()

    try:
        job = db.query(ExecutionJob).filter(ExecutionJob.id == execution_job_id).first()

        if not job:
            return {
                "status": "NO_DATA",
                "message": f"Execution job {execution_job_id} not found.",
            }

        results = (
            db.query(ExecutionResult)
            .filter(ExecutionResult.execution_job_id == execution_job_id)
            .order_by(ExecutionResult.created_at.desc())
            .all()
        )

        latest_result = results[0] if results else None

        return {
            "status": "OK",
            "job": serialize_execution_job(job),
            "compact_payload": _compact_payload(job.payload),
            "results": [serialize_execution_result(row) for row in results],
            "result_summaries": [_summarize_amazon_result(row) for row in results],
            "rollback": {
                "available": _rollback_available(job, latest_result),
                "rollback_action": ROLLBACK_ACTIONS.get(job.action),
                "live_rollback_requires": "dry_run=false and confirm_live=true",
            },
        }

    finally:
        db.close()


def _build_budget_rollback_payload(original, latest_result):
    original_payload = original.payload if isinstance(original.payload, dict) else {}
    decision_payload = original_payload.get("payload") if isinstance(original_payload.get("payload"), dict) else {}

    response_json = latest_result.response_json if latest_result and isinstance(latest_result.response_json, dict) else {}
    previous_budget = response_json.get("current_budget")

    if previous_budget is None:
        return None

    rollback_payload = dict(original_payload)
    rollback_decision_payload = dict(decision_payload)

    rollback_decision_payload["new_budget"] = previous_budget
    rollback_decision_payload["budget"] = previous_budget
    rollback_decision_payload["rollback_previous_budget"] = previous_budget
    rollback_decision_payload["rollback_of_execution_job_id"] = original.id
    rollback_decision_payload["rollback_of_action"] = original.action

    rollback_payload["payload"] = rollback_decision_payload
    rollback_payload["rollback_of_execution_job_id"] = original.id
    rollback_payload["rollback_of_action"] = original.action
    rollback_payload["decision"] = "SET_BUDGET"
    rollback_payload["recommended_action"] = (
        f"Rollback {original.action} from execution job {original.id}; "
        f"restore budget to {previous_budget}."
    )

    return rollback_payload


def rollback_execution(execution_job_id, dry_run=True, confirm_live=False, requested_by="GPT"):
    db = SessionLocal()

    try:
        original = db.query(ExecutionJob).filter(ExecutionJob.id == execution_job_id).first()

        if not original:
            return {
                "status": "NO_DATA",
                "message": f"Execution job {execution_job_id} not found.",
            }

        latest_result = _latest_result_for_job(db, original.id)

        if original.status != "COMPLETED":
            return {
                "status": "REJECTED",
                "message": f"Only completed executions can be rolled back. Current status: {original.status}",
            }

        if original.dry_run:
            return {
                "status": "REJECTED",
                "message": "Dry-run executions do not need rollback.",
            }

        rollback_action = ROLLBACK_ACTIONS.get(original.action)

        if not rollback_action:
            return {
                "status": "REJECTED",
                "message": f"No rollback action is available for {original.action}.",
                "supported_rollback_actions": ROLLBACK_ACTIONS,
            }

        if not _rollback_available(original, latest_result):
            return {
                "status": "REJECTED",
                "message": "Rollback is not available because required before/after audit data is missing.",
            }

        if not dry_run and not confirm_live:
            return {
                "status": "REJECTED",
                "message": "Live rollback requires confirm_live=true.",
            }

        if original.action in ["SET_BUDGET", "INCREASE_BUDGET", "DECREASE_BUDGET"]:
            rollback_payload = _build_budget_rollback_payload(original, latest_result)
            if rollback_payload is None:
                return {
                    "status": "REJECTED",
                    "message": "Budget rollback requires current_budget stored on the original execution result.",
                }
        else:
            rollback_payload = dict(original.payload or {})
            rollback_payload["rollback_of_execution_job_id"] = original.id
            rollback_payload["rollback_of_action"] = original.action
            rollback_payload["decision"] = rollback_action
            rollback_payload["recommended_action"] = f"Rollback {original.action} from execution job {original.id}"

        rollback_job = ExecutionJob(
            decision_id=original.decision_id,
            channel=original.channel,
            profile_id=original.profile_id,
            country_code=original.country_code,
            marketplace=original.marketplace,
            currency=original.currency,
            action=rollback_action,
            status="APPROVED",
            dry_run=dry_run,
            requested_by=requested_by,
            payload=rollback_payload,
            validation_errors=None,
            approved_at=datetime.utcnow(),
        )

        db.add(rollback_job)
        db.commit()
        db.refresh(rollback_job)

        result = run_execution_job(
            rollback_job.id,
            confirm_live=confirm_live,
        )

        return {
            "status": "OK",
            "message": "Rollback execution job created.",
            "original_execution_job_id": original.id,
            "rollback_execution_job_id": rollback_job.id,
            "rollback_action": rollback_action,
            "dry_run": dry_run,
            "confirm_live": confirm_live,
            "result": result,
        }

    except Exception as exc:
        db.rollback()
        return {
            "status": "ERROR",
            "message": "Rollback failed.",
            "error": str(exc),
        }

    finally:
        db.close()
