def build_execution_log_entry(decision_id, decision_type, status, message, payload=None):
    return {
        "decision_id": decision_id,
        "decision_type": decision_type,
        "status": status,
        "message": message,
        "payload": payload or {},
    }
