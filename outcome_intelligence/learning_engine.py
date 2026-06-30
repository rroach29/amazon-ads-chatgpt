"""
Business OS v6.3
Learning Engine

Aggregates outcome and confidence records into a feedback signal that future
optimizers can use to adjust confidence.
"""

from sqlalchemy import text
from database import SessionLocal
from outcome_intelligence.storage import ensure_outcome_tables

LEARNING_SUMMARY_SQL = """
SELECT
    decision_type,
    optimizer_name,
    COUNT(*) AS sample_size,
    AVG(accuracy_percent) AS avg_accuracy,
    AVG(confidence_before) AS avg_confidence_before,
    AVG(confidence_after) AS avg_confidence_after
FROM confidence_history
GROUP BY decision_type, optimizer_name
ORDER BY sample_size DESC, avg_accuracy DESC;
"""

LEARNING_EVENTS_SQL = """
SELECT *
FROM learning_events
ORDER BY created_at DESC
LIMIT :limit;
"""

CONFIDENCE_HISTORY_SQL = """
SELECT *
FROM confidence_history
ORDER BY created_at DESC
LIMIT :limit;
"""


def _row_to_dict(row):
    data = dict(row._mapping)
    for key in ("created_at", "measured_at"):
        if data.get(key):
            data[key] = data[key].isoformat()
    return data


class LearningEngine:
    @staticmethod
    def feedback_summary():
        db = SessionLocal()
        try:
            ensure_outcome_tables(db)
            rows = db.execute(text(LEARNING_SUMMARY_SQL)).fetchall()
            items = [_row_to_dict(row) for row in rows]
            total_samples = sum(int(item.get("sample_size") or 0) for item in items)
            accuracy_values = [float(item.get("avg_accuracy") or 0) for item in items if item.get("avg_accuracy") is not None]
            overall_accuracy = round(sum(accuracy_values) / len(accuracy_values), 2) if accuracy_values else None
            return {
                "status": "OK",
                "total_samples": total_samples,
                "overall_accuracy": overall_accuracy,
                "feedback_by_decision_type": items,
                "narrative": LearningEngine._narrative(total_samples, overall_accuracy, items),
            }
        finally:
            db.close()

    @staticmethod
    def learning_events(limit=100):
        db = SessionLocal()
        try:
            ensure_outcome_tables(db)
            rows = db.execute(text(LEARNING_EVENTS_SQL), {"limit": limit}).fetchall()
            return {"status": "OK", "count": len(rows), "items": [_row_to_dict(row) for row in rows]}
        finally:
            db.close()

    @staticmethod
    def confidence_history(limit=100):
        db = SessionLocal()
        try:
            ensure_outcome_tables(db)
            rows = db.execute(text(CONFIDENCE_HISTORY_SQL), {"limit": limit}).fetchall()
            return {"status": "OK", "count": len(rows), "items": [_row_to_dict(row) for row in rows]}
        finally:
            db.close()

    @staticmethod
    def confidence_adjustment_for(decision_type, optimizer_name=None, default_confidence=70):
        summary = LearningEngine.feedback_summary()
        matches = []
        for item in summary.get("feedback_by_decision_type", []):
            if item.get("decision_type") != decision_type:
                continue
            if optimizer_name and item.get("optimizer_name") != optimizer_name:
                continue
            matches.append(item)

        if not matches:
            return {
                "status": "NO_HISTORY",
                "decision_type": decision_type,
                "optimizer_name": optimizer_name,
                "confidence": default_confidence,
                "message": "No outcome history yet; using default confidence.",
            }

        best = sorted(matches, key=lambda row: int(row.get("sample_size") or 0), reverse=True)[0]
        adjusted = best.get("avg_confidence_after") or default_confidence
        return {
            "status": "OK",
            "decision_type": decision_type,
            "optimizer_name": optimizer_name or best.get("optimizer_name"),
            "confidence": round(float(adjusted), 2),
            "sample_size": best.get("sample_size"),
            "avg_accuracy": best.get("avg_accuracy"),
            "message": "Confidence adjusted using historical outcome accuracy.",
        }

    @staticmethod
    def _narrative(total_samples, overall_accuracy, items):
        if not total_samples:
            return "No outcome learning exists yet. Record outcomes after executions to calibrate future confidence."
        message = f"Business OS has {total_samples} outcome learning samples"
        if overall_accuracy is not None:
            message += f" with average estimate accuracy of {overall_accuracy:.1f}%."
        else:
            message += "."
        if items:
            best = sorted(items, key=lambda row: float(row.get("avg_accuracy") or 0), reverse=True)[0]
            message += f" Strongest current signal: {best.get('decision_type')} via {best.get('optimizer_name')}."
        return message
