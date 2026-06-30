"""
Business OS v3.8.0
Execution Engine with Bid Management

Adds live-supported REDUCE_BID.

REDUCE_BID does not require current_bid in the decision payload.
amazon_execution.py fetches the live current bid before calculating the new bid.
"""

from datetime import datetime
from time import perf_counter

from database import SessionLocal
from marketplace_profiles import get_marketplace_profile
from models import DecisionHistory
from execution_models import ExecutionJob, ExecutionResult
from amazon_execution import execute_amazon_action
from campaign_identity import enrich_payload_with_campaign_identity


SUPPORTED_ACTIONS = {
    "PAUSE_CAMPAIGN",
    "RESUME_CAMPAIGN",
    "INCREASE_BUDGET",
    "DECREASE_BUDGET",
    "SET_BUDGET",
    "REDUCE_BID",
    "SET_BID",
    "ADD_NEGATIVE_KEYWORD",
    "HARVEST_KEYWORD",
    "PROMOTE_TO_EXACT",
}

LIVE_SUPPORTED_ACTIONS = {
    "PAUSE_CAMPAIGN",
    "RESUME_CAMPAIGN",
    "INCREASE_BUDGET",
    "DECREASE_BUDGET",
    "SET_BUDGET",
    "REDUCE_BID",
}


def _normalize_country_code(country_code):
    return str(country_code).upper() if country_code else None


def _payload_dict(decision):
    return decision.payload if isinstance(decision.payload, dict) else {}


def _decision_to_payload(decision, enriched_payload=None):
    payload = enriched_payload if isinstance(enriched_payload, dict) else _payload_dict(decision)

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
    payload = _payload_dict(decision)

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


def _get_payload_value(payload, *keys):
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    return None


def _to_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _validate_execution(
    decision,
    action,
    dry_run,
    confirm_live=False,
    marketplace_context=None,
    payload_override=None,
):
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

    if not dry_run:
        if not confirm_live:
            errors.append("Live execution requires confirm_live=true.")

        if action not in LIVE_SUPPORTED_ACTIONS:
            errors.append(f"Live execution is not yet supported for action: {action}")

    payload = payload_override if isinstance(payload_override, dict) else _payload_dict(decision)

    if action in ["PAUSE_CAMPAIGN", "RESUME_CAMPAIGN", "INCREASE_BUDGET", "DECREASE_BUDGET", "SET_BUDGET", "REDUCE_BID"]:
        if not _get_payload_value(payload, "campaign_id", "campaignId"):
            errors.append("Campaign action requires campaign_id in decision payload.")

        if not dry_run:
            context = marketplace_context if isinstance(marketplace_context, dict) else {}
            if not context.get("profile_id") or not context.get("country_code"):
                errors.append(
                    "Live execution requires resolved profile_id and country_code from marketplace-aware data."
                )

    if action in ["SET_BID", "REDUCE_BID"]:
        if not _get_payload_value(payload, "keyword_id", "keywordId"):
            errors.append("Bid action requires keyword_id in decision payload.")

    if action in ["ADD_NEGATIVE_KEYWORD"]:
        if not payload.get("search_term"):
            errors.append("Negative keyword action requires search_term in decision payload.")

    if action in ["SET_BUDGET", "INCREASE_BUDGET", "DECREASE_BUDGET"]:
        candidate_budget = _get_payload_value(
            payload,
            "new_budget",
            "newBudget",
            "budget",
            "daily_budget",
            "dailyBudget",
            "recommended_budget",
            "recommendedBudget",
            "target_budget",
            "targetBudget",
        )

        percent = _get_payload_value(
            payload,
            "percent",
            "percentage",
            "increase_percent",
            "decrease_percent",
            "change_percent",
            "suggested_budget_increase_percent",
            "suggestedBudgetIncreasePercent",
        )

        amount = _get_payload_value(
            payload,
            "amount",
            "change_amount",
            "increase_amount",
            "decrease_amount",
        )

        if action == "SET_BUDGET" and _to_float(candidate_budget) is None:
            errors.append("SET_BUDGET requires new_budget/budget/recommended_budget in decision payload.")

        if action in ["INCREASE_BUDGET", "DECREASE_BUDGET"]:
            has_final_budget = _to_float(candidate_budget) is not None
            has_delta = _to_float(percent) is not None or _to_float(amount) is not None

            if not has_final_budget and not has_delta:
                errors.append(
                    f"{action} requires either a final budget, percent, or amount. "
                    "current_budget is fetched live from Amazon during execution."
                )

    if action in ["REDUCE_BID"]:
        candidate_bid = _get_payload_value(
            payload,
            "new_bid",
            "newBid",
            "bid",
            "target_bid",
            "targetBid",
            "recommended_bid",
            "recommendedBid",
        )

        percent = _get_payload_value(
            payload,
            "percent",
            "percentage",
            "reduce_percent",
            "reduction_percent",
            "decrease_percent",
            "change_percent",
            "suggested_bid_reduction_percent",
            "suggestedBidReductionPercent",
        )

        amount = _get_payload_value(
            payload,
            "amount",
            "change_amount",
            "reduce_amount",
            "decrease_amount",
        )

        has_final_bid = _to_float(candidate_bid) is not None
        has_delta = _to_float(percent) is not None or _to_float(amount) is not None

        if not has_final_bid and not has_delta:
            errors.append(
                "REDUCE_BID requires either a final bid, reduction percent, or amount. "
                "current_bid is fetched live from Amazon during execution."
            )

    return errors


def create_execution_job(
    decision_id,
    approved=True,
    dry_run=True,
    requested_by="GPT",
    confirm_live=False,
):
    db = SessionLocal()

    try:
        decision = db.query(DecisionHistory).filter(DecisionHistory.id == decision_id).first()

        if not decision:
            return {"status": "ERROR", "message": f"Decision {decision_id} not found."}

        action = decision.decision
        raw_context = _extract_marketplace_from_decision(decision)
        raw_payload = _payload_dict(decision)

        identity_result = {"status": "SKIPPED", "message": "No campaign identity lookup required."}
        enriched_payload = raw_payload
        marketplace_context = raw_context

        if action in ["PAUSE_CAMPAIGN", "RESUME_CAMPAIGN", "INCREASE_BUDGET", "DECREASE_BUDGET", "SET_BUDGET", "REDUCE_BID"]:
            identity_result = enrich_payload_with_campaign_identity(
                payload=raw_payload,
                existing_context=raw_context,
            )

            if identity_result.get("status") == "OK":
                enriched_payload = identity_result.get("payload", raw_payload)
                marketplace_context = identity_result.get("context", raw_context)

        validation_errors = []

        if (
            action in ["PAUSE_CAMPAIGN", "RESUME_CAMPAIGN", "INCREASE_BUDGET", "DECREASE_BUDGET", "SET_BUDGET", "REDUCE_BID"]
            and identity_result.get("status") != "OK"
        ):
            validation_errors.append(
                f"Campaign identity could not be resolved safely: {identity_result.get('message')}"
            )

        validation_errors.extend(
            _validate_execution(
                decision,
                action,
                dry_run=dry_run,
                confirm_live=confirm_live,
                marketplace_context=marketplace_context,
                payload_override=enriched_payload,
            )
        )

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
            payload=_decision_to_payload(decision, enriched_payload=enriched_payload),
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
                "identity_resolution": identity_result,
                "validation_errors": validation_errors,
            }

        result = run_execution_job(job.id, confirm_live=confirm_live)

        return {
            "status": "OK",
            "message": "Execution job created.",
            "execution_job_id": job.id,
            "dry_run": dry_run,
            "confirm_live": confirm_live,
            "identity_resolution": identity_result,
            "result": result,
        }

    except Exception as exc:
        db.rollback()
        return {"status": "ERROR", "message": "Failed to create execution job.", "error": str(exc)}

    finally:
        db.close()


def run_execution_job(execution_job_id, confirm_live=False):
    db = SessionLocal()
    start = perf_counter()

    try:
        job = db.query(ExecutionJob).filter(ExecutionJob.id == execution_job_id).first()

        if not job:
            return {"status": "ERROR", "message": f"Execution job {execution_job_id} not found."}

        if job.status not in ["APPROVED", "PENDING"]:
            return {
                "status": "SKIPPED",
                "message": f"Execution job has non-runnable status: {job.status}",
                "execution_job_id": job.id,
            }

        if not job.dry_run and not confirm_live:
            return {
                "status": "REJECTED",
                "message": "Live execution requires confirm_live=true.",
                "execution_job_id": job.id,
            }

        if not job.dry_run and (not job.profile_id or not job.country_code):
            return {
                "status": "REJECTED",
                "message": "Live execution rejected because identity was not resolved to profile_id/country_code.",
                "execution_job_id": job.id,
            }

        job.status = "RUNNING"
        job.started_at = datetime.utcnow()
        db.commit()

        job_payload = job.payload or {}
        decision_payload = job_payload.get("payload", {}) if isinstance(job_payload, dict) else {}

        adapter_result = execute_amazon_action(
            action=job.action,
            profile_id=job.profile_id,
            country_code=job.country_code,
            payload=decision_payload,
            dry_run=job.dry_run,
        )

        elapsed_ms = round((perf_counter() - start) * 1000, 2)
        success = bool(adapter_result.get("success"))
        result_status = "COMPLETED" if success else "FAILED"

        result = ExecutionResult(
            execution_job_id=job.id,
            decision_id=job.decision_id,
            success=success,
            dry_run=job.dry_run,
            amazon_request_id=adapter_result.get("amazon_request_id"),
            http_status=adapter_result.get("http_status"),
            action=job.action,
            status=result_status,
            response_json=adapter_result,
            error_message=adapter_result.get("error_message"),
            execution_time_ms=elapsed_ms,
        )

        job.status = result_status
        job.completed_at = datetime.utcnow()
        db.add(result)

        if success and not job.dry_run:
            decision = db.query(DecisionHistory).filter(DecisionHistory.id == job.decision_id).first()
            if decision:
                decision.status = "EXECUTED"
                decision.outcome = "EXECUTED_LIVE"
                decision.evaluated_at = datetime.utcnow()
                decision.notes = "Executed live through Business OS v3.8.0."

        db.commit()
        db.refresh(result)

        return {
            "status": "OK" if success else "ERROR",
            "message": "Execution completed." if success else "Execution failed.",
            "execution_job_id": job.id,
            "execution_result_id": result.id,
            "dry_run": job.dry_run,
            "response": adapter_result,
        }

    except Exception as exc:
        db.rollback()

        try:
            job = db.query(ExecutionJob).filter(ExecutionJob.id == execution_job_id).first()
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
        return {"status": "OK", "count": len(rows), "items": [serialize_execution_job(row) for row in rows]}
    finally:
        db.close()


def get_execution_job(execution_job_id):
    db = SessionLocal()
    try:
        job = db.query(ExecutionJob).filter(ExecutionJob.id == execution_job_id).first()
        if not job:
            return {"status": "NO_DATA", "message": f"Execution job {execution_job_id} not found."}

        results = (
            db.query(ExecutionResult)
            .filter(ExecutionResult.execution_job_id == execution_job_id)
            .order_by(ExecutionResult.created_at.desc())
            .all()
        )

        return {
            "status": "OK",
            "job": serialize_execution_job(job),
            "results": [serialize_execution_result(row) for row in results],
        }
    finally:
        db.close()


def cancel_execution_job(execution_job_id):
    db = SessionLocal()
    try:
        job = db.query(ExecutionJob).filter(ExecutionJob.id == execution_job_id).first()
        if not job:
            return {"status": "NO_DATA", "message": f"Execution job {execution_job_id} not found."}

        if job.status in ["COMPLETED", "FAILED", "CANCELLED"]:
            return {
                "status": "SKIPPED",
                "message": f"Execution job is already terminal: {job.status}",
                "job": serialize_execution_job(job),
            }

        job.status = "CANCELLED"
        job.completed_at = datetime.utcnow()
        db.commit()

        return {"status": "OK", "message": "Execution job cancelled.", "job": serialize_execution_job(job)}
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
