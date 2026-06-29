from sqlalchemy import text
from database import SessionLocal

CREATE_DECISION_LEARNING_SQL = """
CREATE TABLE IF NOT EXISTS decision_learning (
    id SERIAL PRIMARY KEY,
    decision_history_id INTEGER,
    decision_type VARCHAR(100),
    estimated_impact DOUBLE PRECISION DEFAULT 0,
    actual_impact DOUBLE PRECISION,
    accuracy_percent DOUBLE PRECISION,
    confidence_before DOUBLE PRECISION,
    confidence_after DOUBLE PRECISION,
    days_until_measured INTEGER DEFAULT 7,
    measured_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    notes TEXT
);
"""

SELECT_LEARNING_SQL = """
SELECT
    id,
    decision_history_id,
    decision_type,
    estimated_impact,
    actual_impact,
    accuracy_percent,
    confidence_before,
    confidence_after,
    days_until_measured,
    measured_at,
    notes
FROM decision_learning
ORDER BY measured_at DESC
LIMIT :limit;
"""

SUMMARY_SQL = """
SELECT
    decision_type,
    COUNT(*) AS total_records,
    AVG(accuracy_percent) AS avg_accuracy,
    AVG(confidence_before) AS avg_confidence_before,
    AVG(confidence_after) AS avg_confidence_after,
    AVG(actual_impact) AS avg_actual_impact,
    SUM(actual_impact) AS total_actual_impact
FROM decision_learning
GROUP BY decision_type
ORDER BY total_records DESC;
"""


def ensure_decision_learning_table(db):
    db.execute(text(CREATE_DECISION_LEARNING_SQL))
    db.commit()


def _row_to_dict(row):
    data = dict(row._mapping)
    if data.get("measured_at"):
        data["measured_at"] = data["measured_at"].isoformat()
    return data


def get_learning_records(limit=100):
    db = SessionLocal()

    try:
        ensure_decision_learning_table(db)
        rows = db.execute(text(SELECT_LEARNING_SQL), {"limit": limit}).fetchall()
        return {
            "status": "OK",
            "count": len(rows),
            "items": [_row_to_dict(row) for row in rows],
        }

    finally:
        db.close()


def get_learning_summary():
    db = SessionLocal()

    try:
        ensure_decision_learning_table(db)
        rows = db.execute(text(SUMMARY_SQL)).fetchall()
        items = [_row_to_dict(row) for row in rows]

        total_records = sum(item.get("total_records") or 0 for item in items)
        avg_accuracy_values = [
            float(item.get("avg_accuracy") or 0)
            for item in items
            if item.get("avg_accuracy") is not None
        ]
        overall_accuracy = (
            round(sum(avg_accuracy_values) / len(avg_accuracy_values), 2)
            if avg_accuracy_values else None
        )

        return {
            "status": "OK",
            "total_records": total_records,
            "overall_accuracy": overall_accuracy,
            "by_decision_type": items,
        }

    finally:
        db.close()
