"""
Business OS v3.6.1
Execution Limits

Centralized safety limits for execution planning and batch execution.
"""

DEFAULT_EXECUTION_LIMITS = {
    "max_batch_size": 10,
    "max_live_batch_size": 5,
    "max_high_risk_live_items": 0,
    "min_live_confidence": 70,
    "allowed_live_priorities": ["HIGH", "MEDIUM"],
    "blocked_live_risks": ["HIGH"],
}


def get_execution_limits():
    return {
        "status": "OK",
        "limits": DEFAULT_EXECUTION_LIMITS,
    }


def check_batch_limits(steps, dry_run=True):
    errors = []
    warnings = []

    limits = DEFAULT_EXECUTION_LIMITS
    steps = steps or []

    if len(steps) > limits["max_batch_size"]:
        errors.append(
            f"Batch has {len(steps)} items; maximum is {limits['max_batch_size']}."
        )

    if not dry_run and len(steps) > limits["max_live_batch_size"]:
        errors.append(
            f"Live batch has {len(steps)} items; maximum live batch size is {limits['max_live_batch_size']}."
        )

    high_risk_count = sum(1 for step in steps if step.get("risk") == "HIGH")
    if not dry_run and high_risk_count > limits["max_high_risk_live_items"]:
        errors.append("High-risk decisions cannot be batch executed live.")

    for step in steps:
        if not dry_run:
            confidence = step.get("confidence") or 0
            if confidence < limits["min_live_confidence"]:
                errors.append(
                    f"Decision {step.get('decision_id')} confidence {confidence} is below live minimum {limits['min_live_confidence']}."
                )

            if step.get("priority") not in limits["allowed_live_priorities"]:
                errors.append(
                    f"Decision {step.get('decision_id')} priority {step.get('priority')} is not allowed for live execution."
                )

            if step.get("risk") in limits["blocked_live_risks"]:
                errors.append(
                    f"Decision {step.get('decision_id')} risk {step.get('risk')} blocks live execution."
                )

            if not step.get("ready_for_live_execution"):
                errors.append(
                    f"Decision {step.get('decision_id')} is not ready for live execution."
                )

        if step.get("metadata", {}).get("supported") is False:
            warnings.append(
                f"Decision {step.get('decision_id')} action {step.get('action')} is not supported yet."
            )

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "limits": limits,
    }
