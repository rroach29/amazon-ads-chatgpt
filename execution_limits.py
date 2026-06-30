"""
Business OS v3.6.0
Execution Limits

Central safety limits for batch execution. These are deliberately conservative.
"""

DEFAULT_LIMITS = {
    "max_batch_size": 10,
    "max_live_batch_size": 5,
    "max_high_risk_live_items": 0,
    "min_live_confidence": 70,
    "allowed_live_priorities": ["HIGH", "MEDIUM"],
    "blocked_live_risks": ["HIGH"],
}


def get_execution_limits():
    return {"status": "OK", "limits": DEFAULT_LIMITS}


def evaluate_batch_limits(decisions, dry_run=True, limits=None):
    limits = limits or DEFAULT_LIMITS
    decisions = decisions or []
    errors = []
    warnings = []

    if len(decisions) > limits["max_batch_size"]:
        errors.append(f"Batch size {len(decisions)} exceeds max_batch_size {limits['max_batch_size']}.")

    if not dry_run and len(decisions) > limits["max_live_batch_size"]:
        errors.append(f"Live batch size {len(decisions)} exceeds max_live_batch_size {limits['max_live_batch_size']}.")

    high_risk = [d for d in decisions if str(d.get("risk") or "").upper() == "HIGH"]
    if not dry_run and len(high_risk) > limits["max_high_risk_live_items"]:
        errors.append("Live batch contains HIGH risk decisions, which are blocked by policy.")

    for decision in decisions:
        confidence = decision.get("confidence") or 0
        try:
            confidence = float(confidence)
        except Exception:
            confidence = 0

        if not dry_run and confidence < limits["min_live_confidence"]:
            errors.append(
                f"Decision {decision.get('id')} confidence {confidence} is below live threshold {limits['min_live_confidence']}."
            )

        priority = str(decision.get("priority") or "").upper()
        if not dry_run and priority not in limits["allowed_live_priorities"]:
            warnings.append(f"Decision {decision.get('id')} has non-standard live priority: {priority}.")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "limits": limits,
    }
