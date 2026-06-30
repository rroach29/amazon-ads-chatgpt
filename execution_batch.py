"""
Business OS v3.6.1
Batch Execution

Uses the enriched execution plan before executing any decisions.
"""

from execution_planner import build_execution_plan
from execution_engine import create_execution_job


def execute_batch(decision_ids, dry_run=True, confirm_live=False, requested_by="GPT"):
    plan = build_execution_plan(decision_ids=decision_ids, dry_run=dry_run)

    if plan.get("status") != "OK":
        return plan

    limit_check = plan.get("limit_check", {})
    if not limit_check.get("ok"):
        return {
            "status": "REJECTED",
            "message": "Batch failed execution limit validation.",
            "plan": plan,
        }

    results = []

    for step in plan.get("steps", []):
        if not step.get("ready_for_live_execution") and not dry_run:
            results.append({
                "decision_id": step.get("decision_id"),
                "status": "SKIPPED",
                "message": "Decision is not ready for live execution.",
                "blockers": step.get("blockers"),
            })
            continue

        if step.get("metadata", {}).get("supported") is False:
            results.append({
                "decision_id": step.get("decision_id"),
                "status": "SKIPPED",
                "message": "Action is not supported yet.",
                "metadata": step.get("metadata"),
            })
            continue

        result = create_execution_job(
            decision_id=step.get("decision_id"),
            approved=True,
            dry_run=dry_run,
            requested_by=requested_by,
            confirm_live=confirm_live,
        )

        results.append({
            "decision_id": step.get("decision_id"),
            "status": result.get("status"),
            "result": result,
        })

    return {
        "status": "OK",
        "dry_run": dry_run,
        "confirm_live": confirm_live,
        "plan": plan,
        "results": results,
    }
