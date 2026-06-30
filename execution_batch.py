"""
Business OS v3.6.0
Batch Execution

Queues and executes multiple decisions through the existing v3.4/v3.5 execution
pipeline. Dry-run remains the default.
"""

from execution_planner import build_execution_plan
from execution_engine import create_execution_job, list_execution_jobs


def execute_decision_batch(
    decision_ids,
    approved=True,
    dry_run=True,
    confirm_live=False,
    requested_by="GPT",
    stop_on_error=True,
):
    plan = build_execution_plan(decision_ids, dry_run=dry_run)

    if plan.get("missing_decision_ids"):
        return {
            "status": "REJECTED",
            "message": "One or more decision IDs were not found.",
            "plan": plan,
        }

    if not plan.get("limit_check", {}).get("ok"):
        return {
            "status": "REJECTED",
            "message": "Batch failed safety limit validation.",
            "plan": plan,
        }

    if not dry_run and not confirm_live:
        return {
            "status": "REJECTED",
            "message": "Live batch execution requires confirm_live=true.",
            "plan": plan,
        }

    results = []
    failures = []

    for step in plan.get("steps", []):
        decision_id = step.get("decision_id")
        result = create_execution_job(
            decision_id=decision_id,
            approved=approved,
            dry_run=dry_run,
            confirm_live=confirm_live,
            requested_by=requested_by,
        )
        results.append(result)

        if result.get("status") not in ["OK"]:
            failures.append({"decision_id": decision_id, "result": result})
            if stop_on_error:
                break

    return {
        "status": "OK" if not failures else "PARTIAL_SUCCESS",
        "message": "Batch execution completed." if not failures else "Batch execution completed with failures.",
        "dry_run": dry_run,
        "confirm_live": confirm_live,
        "planned": len(plan.get("steps", [])),
        "attempted": len(results),
        "failures": failures,
        "plan": plan,
        "results": results,
    }


def get_execution_queue(status="APPROVED", limit=50):
    return list_execution_jobs(status=status, limit=limit)
