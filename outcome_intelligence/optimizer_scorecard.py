"""
Business OS v6.3
Optimizer Scorecard

Ranks optimizers by measured outcome quality. When optimizer metadata is not yet
present in historic decisions, records are grouped as `unknown`, preserving
compatibility while still exposing the platform metric.
"""

from sqlalchemy import text
from database import SessionLocal
from outcome_intelligence.storage import ensure_outcome_tables

SCORECARD_SQL = """
SELECT
    optimizer_name,
    decision_type,
    COUNT(*) AS outcomes_recorded,
    AVG(actual_impact) AS avg_actual_impact,
    SUM(actual_impact) AS total_actual_impact,
    AVG(variance_percent) AS avg_variance_percent,
    SUM(CASE WHEN outcome_status = 'SUCCESS' THEN 1 ELSE 0 END) AS success_count,
    SUM(CASE WHEN outcome_status = 'FAILED' THEN 1 ELSE 0 END) AS failure_count
FROM decision_outcomes
GROUP BY optimizer_name, decision_type
ORDER BY total_actual_impact DESC NULLS LAST, outcomes_recorded DESC;
"""


def _row_to_dict(row):
    item = dict(row._mapping)
    success = int(item.get("success_count") or 0)
    failure = int(item.get("failure_count") or 0)
    total = success + failure
    item["success_rate"] = round((success / total) * 100, 2) if total else None
    return item


class OptimizerScorecard:
    @staticmethod
    def scorecard():
        db = SessionLocal()
        try:
            ensure_outcome_tables(db)
            rows = db.execute(text(SCORECARD_SQL)).fetchall()
            items = [_row_to_dict(row) for row in rows]
            best = items[0] if items else None
            return {
                "status": "OK",
                "count": len(items),
                "best_optimizer_signal": best,
                "items": items,
                "narrative": OptimizerScorecard._narrative(items),
            }
        finally:
            db.close()

    @staticmethod
    def _narrative(items):
        if not items:
            return "No optimizer outcome scorecard exists yet. Record decision outcomes to rank optimizer performance."
        best = items[0]
        return (
            f"Top current optimizer signal is {best.get('optimizer_name')} for "
            f"{best.get('decision_type')} with {best.get('outcomes_recorded')} recorded outcomes."
        )
