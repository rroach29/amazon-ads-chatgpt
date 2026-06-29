"""
Business OS v3.4.1
Execution Framework Engine

This release creates execution jobs and dry-run execution results.

It does NOT mutate Amazon Ads yet.
Live Amazon API execution begins in v3.4.2.
"""

from datetime import datetime
from time import perf_counter

from database import SessionLocal
from marketplace_profiles import get_marketplace_profile
from models import DecisionHistory
from execution_models import ExecutionJob, ExecutionResult


SUPPORTED_ACTIONS = {
    "PAUSE_CAMPAIGN",
    "RESUME_CAMPAIGN",
    "INCREASE_BUDGET",
    "DECREASE_BUDGET",
    "SET_BUDGET",
    "SET_BID",
    "ADD_NEGATIVE_KEYWORD",
    "HARVEST_KEYWORD",
    "PROMOTE_TO_EXACT",
}


def _normalize_country_code(country_code):
    return str(country_code).upper() if country_code else None


def _decision_to_payload(decision):
    payload = decision.payload if isinstance(decision.payload, dict) else {}

    return {
        "decision_id": decision.id,
        "decision": decision.decision,
        "priority": decision.priority,
        "confidence": decision.confidence,
        "risk": decision.risk,
        "recommended_action": decision.recommended_action,
        "estimated_monthly_impact": decision.estimated_monthly_impact,
        "payload": payload,
    }


def _extract_marketplace_from_decision(decision):
    payload = decision.payload if isinstance(decision.payload, dict) else {}

    country_code = (
        payload.get("country_code")
        or payload.get("marketplace_country_code")
        or payload.get("country")
    )

    profile_id = payload.get("profile_id")
    marketplace = payload.get("marketplace")
    currency = payload.get("currency")

    if country_code and (not profile_id or not marketplace or not currency):
        try:
            profile_response = get_marketplace_profile(country_code)
            if profile_response.get("status") == "OK":
                profile = profile_response.get("profile", {})
                profile_id = profile_id or profile.get("profile_id")
                marketplace = marketplace or profile.get("marketplace")
                currency = currency or profile.get("currency")
        except Exception:
            pass

    return {
        "profile_id": str(profile_id) if profile_id else None,
        "country_code": _normalize_country_code(country_code),
        "marketplace": marketplace,
        "currency": currency,
    }


def _validate_execution(decision, action, dry_run):
    errors = []

    if not decision:
        errors.append("Decision not found.")
        return errors

    if decision.status not in ["OPEN", "APPROVED", "PENDING"]:
        errors.append(f"Decision status is not executable: {decision.status}")

    if not action:
        errors.append("Missing execution action.")

    if action and action not in SUPPORTED_ACTIONS:
        errors.append(f"Unsupported execution action: {action}")

    payload = decision.payload if isinstance(decision.payload, dict) else {}

    if action in ["PAUSE_CAMPAIGN", "RESUME_CAMPAIGN", "INCREASE_BUDGET", "DECREASE_BUDGET", "SET_BUDGET"]:
        if not payload.get("campaign_id") and not payload.get("campaignId"):
            errors.append("Campaign action requires campaign_id in decision payload.")

    if action in ["SET_BID"]:
        if not payload.get("target_id") and not payload.get("keyword_id"):
            errors.append("Bid action requires target_id or keyword_id in decision payload.")

    if action in ["ADD_NEGATIVE_KEYWORD"]:
        if not payload.get("search_term"):
            errors.append("Negative keyword action requires search_term in decision payload.")

    # v3.4.1 is dry-run only. Do not allow live mutation yet.
    if dry_run is False:
        errors.append("Live execution is not enabled in v3.4.1. Use dry_run=true.")

    return errors


def create_execution_job(decision_id, approved=True, dry_run=True, requested_by="GPT"):
    db = SessionLocal()

    try:
        decision = (
            db.query(DecisionHistory)
            .filter(DecisionHistory.id == decision_id)
            .first()
        )

        if not decision:
            return {
                "status": "ERROR",
                "message": f"Decision {decision_id} not found.",
            }

        action = decision.decision
        marketplace_context = _extract_marketplace_from_decision(decision)
        validation_errors = _validate_execution(decision, action, dry_run)

        job_status = "APPROVED" if approved and not validation_errors else "REJECTED"

        job = ExecutionJob(
            decision_id=decision.id,
            channel=decision.channel,
            profile_id=marketplace_context.get("profile_id"),
            country_code=marketplace_context.get("country_code"),
            marketplace=marketplace_context.get("marketplace"),
            currency=marketplace_context.get("currency"),
            action=action,
            status=job_status,
            dry_run=dry_run,
            requested_by=requested_by,
            payload=_decision_to_payload(decision),
            validation_errors=validation_errors,
            approved_at=datetime.utcnow() if approved and not validation_errors else None,
        )

        db.add(job)
        db.commit()
        db.refresh(job)

        if validation_errors:
            return {
                "status": "REJECTED",
                "message": "Execution job was rejected by validation.",
                "execution_job_id": job.id,
                "validation_errors": validation_errors,
            }

        result = run_execution_job(job.id)

        return {
            "status": "OK",
            "message": "Execution job created.",
            "execution_job_id": job.id,
            "dry_run": dry_run,
            "result": result,
        }

    except Exception as exc:
        db.rollback()
        return {
            "status": "ERROR",
            "message": "Failed to create execution job.",
            "error": str(exc),
        }

    finally:
        db.close()


def run_execution_job(execution_job_id):
    db = SessionLocal()
    start = perf_counter()

    try:
        job = (
            db.query(ExecutionJob)
            .filter(ExecutionJob.id == execution_job_id)
            .first()
        )

        if not job:
            return {
                "status": "ERROR",
                "message": f"Execution job {execution_job_id} not found.",
            }

        if job.status not in ["APPROVED", "PENDING"]:
            return {
                "status": "SKIPPED",
                "message": f"Execution job has non-runnable status: {job.status}",
                "execution_job_id": job.id,
            }

        job.status = "RUNNING"
        job.started_at = datetime.utcnow()
        db.commit()

        # v3.4.1 framework-only dry-run result.
        simulated_response = {
            "mode": "dry_run",
            "action": job.action,
            "decision_id": job.decision_id,
            "profile_id": job.profile_id,
            "country_code": job.country_code,
            "marketplace": job.marketplace,
            "message": "Dry-run execution succeeded. No Amazon Ads changes were made.",
            "next_release": "v3.4.2 will replace this dry-run handler with live Amazon Ads API calls.",
        }

        elapsed_ms = round((perf_counter() - start) * 1000, 2)

        result = ExecutionResult(
            execution_job_id=job.id,
            decision_id=job.decision_id,
            success=True,
            dry_run=True,
            amazon_request_id=None,
            http_status=None,
            action=job.action,
            status="COMPLETED",
            response_json=simulated_response,
            error_message=None,
            execution_time_ms=elapsed_ms,
        )

        job.status = "COMPLETED"
        job.completed_at = datetime.utcnow()

        db.add(result)
        db.commit()
        db.refresh(result)

        return {
            "status": "OK",
            "message": "Dry-run execution completed.",
            "execution_job_id": job.id,
            "execution_result_id": result.id,
            "response": simulated_response,
        }

    except Exception as exc:
        db.rollback()

        try:
            job = (
                db.query(ExecutionJob)
                .filter(ExecutionJob.id == execution_job_id)
                .first()
            )

            if job:
                job.status = "FAILED"
                job.completed_at = datetime.utcnow()

                elapsed_ms = round((perf_counter() - start) * 1000, 2)

                result = ExecutionResult(
                    execution_job_id=job.id,
                    decision_id=job.decision_id,
                    success=False,
                    dry_run=job.dry_run,
                    action=job.action,
                    status="FAILED",
                    error_message=str(exc),
                    execution_time_ms=elapsed_ms,
                )

                db.add(result)
                db.commit()

        except Exception:
            db.rollback()

        return {
            "status": "ERROR",
            "message": "Execution failed.",
            "execution_job_id": execution_job_id,
            "error": str(exc),
        }

    finally:
        db.close()


def list_execution_jobs(status=None, limit=50):
    db = SessionLocal()

    try:
        query = db.query(ExecutionJob).order_by(ExecutionJob.created_at.desc())

        if status:
            query = query.filter(ExecutionJob.status == status)

        rows = query.limit(limit).all()

        return {
            "status": "OK",
            "count": len(rows),
            "items": [
                serialize_execution_job(row)
                for row in rows
            ],
        }

    finally:
        db.close()


def get_execution_job(execution_job_id):
    db = SessionLocal()

    try:
        job = (
            db.query(ExecutionJob)
            .filter(ExecutionJob.id == execution_job_id)
            .first()
        )

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

        return {
            "status": "OK",
            "job": serialize_execution_job(job),
            "results": [
                serialize_execution_result(row)
                for row in results
            ],
        }

    finally:
        db.close()


def cancel_execution_job(execution_job_id):
    db = SessionLocal()

    try:
        job = (
            db.query(ExecutionJob)
            .filter(ExecutionJob.id == execution_job_id)
            .first()
        )

        if not job:
            return {
                "status": "NO_DATA",
                "message": f"Execution job {execution_job_id} not found.",
            }

        if job.status in ["COMPLETED", "FAILED", "CANCELLED"]:
            return {
                "status": "SKIPPED",
                "message": f"Execution job is already terminal: {job.status}",
                "job": serialize_execution_job(job),
            }

        job.status = "CANCELLED"
        job.completed_at = datetime.utcnow()
        db.commit()

        return {
            "status": "OK",
            "message": "Execution job cancelled.",
            "job": serialize_execution_job(job),
        }

    finally:
        db.close()


def serialize_execution_job(job):
    return {
        "id": job.id,
        "decision_id": job.decision_id,
        "channel": job.channel,
        "profile_id": job.profile_id,
        "country_code": job.country_code,
        "marketplace": job.marketplace,
        "currency": job.currency,
        "action": job.action,
        "status": job.status,
        "dry_run": job.dry_run,
        "requested_by": job.requested_by,
        "payload": job.payload,
        "validation_errors": job.validation_errors,
        "requested_at": job.requested_at.isoformat() if job.requested_at else None,
        "approved_at": job.approved_at.isoformat() if job.approved_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


def serialize_execution_result(result):
    return {
        "id": result.id,
        "execution_job_id": result.execution_job_id,
        "decision_id": result.decision_id,
        "success": result.success,
        "dry_run": result.dry_run,
        "amazon_request_id": result.amazon_request_id,
        "http_status": result.http_status,
        "action": result.action,
        "status": result.status,
        "response_json": result.response_json,
        "error_message": result.error_message,
        "execution_time_ms": result.execution_time_ms,
        "created_at": result.created_at.isoformat() if result.created_at else None,
    }
