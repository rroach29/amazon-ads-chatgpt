from datetime import datetime, timezone
from sqlalchemy import text

from database import SessionLocal


CREATE_EXECUTION_LOGS_SQL = """
CREATE TABLE IF NOT EXISTS execution_logs (
    id SERIAL PRIMARY KEY,
    decision_id INTEGER,
    decision_type VARCHAR(100),
    status VARCHAR(50),
    dry_run BOOLEAN DEFAULT TRUE,
    undo_supported BOOLEAN DEFAULT FALSE,
    undo_action VARCHAR(100),
    message TEXT,
    amazon_request JSONB,
    amazon_response JSONB,
    execution_result JSONB,
    error TEXT,
    executed_by VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
"""


INSERT_EXECUTION_LOG_SQL = """
INSERT INTO execution_logs (
    decision_id,
    decision_type,
    status,
    dry_run,
    undo_supported,
    undo_action,
    message,
    amazon_request,
    amazon_response,
    execution_result,
    error,
    executed_by,
    created_at
)
VALUES (
    :decision_id,
    :decision_type,
    :status,
    :dry_run,
    :undo_supported,
    :undo_action,
    :message,
    CAST(:amazon_request AS JSONB),
    CAST(:amazon_response AS JSONB),
    CAST(:execution_result AS JSONB),
    :error,
    :executed_by,
    :created_at
)
RETURNING id;
"""


SELECT_EXECUTION_LOGS_SQL = """
SELECT
    id,
    decision_id,
    decision_type,
    status,
    dry_run,
    undo_supported,
    undo_action,
    message,
    amazon_request,
    amazon_response,
    execution_result,
    error,
    executed_by,
    created_at
FROM execution_logs
ORDER BY created_at DESC
LIMIT :limit;
"""


SELECT_EXECUTION_LOG_BY_DECISION_SQL = """
SELECT
    id,
    decision_id,
    decision_type,
    status,
    dry_run,
    undo_supported,
    undo_action,
    message,
    amazon_request,
    amazon_response,
    execution_result,
    error,
    executed_by,
    created_at
FROM execution_logs
WHERE decision_id = :decision_id
ORDER BY created_at DESC
LIMIT :limit;
"""


def _json(value):
    import json
    return json.dumps(value or {})


def ensure_execution_logs_table(db):
    db.execute(text(CREATE_EXECUTION_LOGS_SQL))
    db.commit()


def create_execution_log(
    decision_id=None,
    decision_type=None,
    status="UNKNOWN",
    dry_run=True,
    undo_supported=False,
    undo_action=None,
    message=None,
    amazon_request=None,
    amazon_response=None,
    execution_result=None,
    error=None,
    executed_by="ChatGPT",
):
    db = SessionLocal()

    try:
        ensure_execution_logs_table(db)

        result = db.execute(
            text(INSERT_EXECUTION_LOG_SQL),
            {
                "decision_id": decision_id,
                "decision_type": decision_type,
                "status": status,
                "dry_run": dry_run,
                "undo_supported": undo_supported,
                "undo_action": undo_action,
                "message": message,
                "amazon_request": _json(amazon_request),
                "amazon_response": _json(amazon_response),
                "execution_result": _json(execution_result),
                "error": error,
                "executed_by": executed_by,
                "created_at": datetime.now(timezone.utc),
            },
        )

        log_id = result.scalar()
        db.commit()

        return {
            "status": "OK",
            "log_id": log_id,
        }

    except Exception as exc:
        db.rollback()
        return {
            "status": "ERROR",
            "message": "Failed to create execution log.",
            "error": str(exc),
        }

    finally:
        db.close()


def _row_to_dict(row):
    data = dict(row._mapping)

    if data.get("created_at"):
        data["created_at"] = data["created_at"].isoformat()

    return data


def get_execution_history(limit=100):
    db = SessionLocal()

    try:
        ensure_execution_logs_table(db)
        rows = db.execute(text(SELECT_EXECUTION_LOGS_SQL), {"limit": limit}).fetchall()

        return {
            "status": "OK",
            "count": len(rows),
            "items": [_row_to_dict(row) for row in rows],
        }

    finally:
        db.close()


def get_execution_history_for_decision(decision_id, limit=25):
    db = SessionLocal()

    try:
        ensure_execution_logs_table(db)
        rows = db.execute(
            text(SELECT_EXECUTION_LOG_BY_DECISION_SQL),
            {"decision_id": decision_id, "limit": limit},
        ).fetchall()

        return {
            "status": "OK",
            "decision_id": decision_id,
            "count": len(rows),
            "items": [_row_to_dict(row) for row in rows],
        }

    finally:
        db.close()
