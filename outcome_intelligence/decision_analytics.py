"""
Business OS v6.3
Decision Analytics

Scorecard for how the Business OS is performing as a decision-making system.
"""

from sqlalchemy import text
from database import SessionLocal
from outcome_intelligence.storage import ensure_outcome_tables

DECISION_ANALYTICS_SQL = """
SELECT
    decision AS decision_type,
    COUNT(*) AS total_decisions,
    SUM(CASE WHEN status IN ('ACKNOWLEDGED', 'APPROVED', 'EXECUTED', 'SIMULATED') THEN 1 ELSE 0 END) AS touched_decisions,
    SUM(CASE WHEN status IN ('EXECUTED', 'SIMULATED') THEN 1 ELSE 0 END) AS executed_or_simulated,
    AVG(confidence) AS avg_confidence,
    SUM(estimated_monthly_impact) AS total_estimated_impact,
    AVG(estimated_monthly_impact) AS avg_estimated_impact,
    SUM(COALESCE(actual_impact, 0)) AS total_actual_impact,
    AVG(actual_impact) AS avg_actual_impact,
    SUM(CASE WHEN was_correct = true THEN 1 ELSE 0 END) AS correct_count,
    SUM(CASE WHEN was_correct = false THEN 1 ELSE 0 END) AS incorrect_count
FROM decision_history
GROUP BY decision
ORDER BY total_decisions DESC;
"""

OUTCOME_ANALYTICS_SQL = """
SELECT
    decision_type,
    optimizer_name,
    COUNT(*) AS outcome_count,
    AVG(variance) AS avg_variance,
    AVG(variance_percent) AS avg_variance_percent,
    AVG(actual_impact) AS avg_actual_impact,
    SUM(actual_impact) AS total_actual_impact,
    SUM(CASE WHEN outcome_status = 'SUCCESS' THEN 1 ELSE 0 END) AS success_count,
    SUM(CASE WHEN outcome_status = 'FAILED' THEN 1 ELSE 0 END) AS failure_count
FROM decision_outcomes
GROUP BY decision_type, optimizer_name
ORDER BY outcome_count DESC;
"""


def _row_to_dict(row):
    return dict(row._mapping)


class DecisionAnalytics:
    @staticmethod
    def analytics():
        db = SessionLocal()
        try:
            ensure_outcome_tables(db)
            decision_rows = db.execute(text(DECISION_ANALYTICS_SQL)).fetchall()
            outcome_rows = db.execute(text(OUTCOME_ANALYTICS_SQL)).fetchall()

            by_decision_type = [_row_to_dict(row) for row in decision_rows]
            by_outcome = [_row_to_dict(row) for row in outcome_rows]

            total_decisions = sum(int(item.get("total_decisions") or 0) for item in by_decision_type)
            total_estimated = sum(float(item.get("total_estimated_impact") or 0) for item in by_decision_type)
            total_actual = sum(float(item.get("total_actual_impact") or 0) for item in by_decision_type)
            correct = sum(int(item.get("correct_count") or 0) for item in by_decision_type)
            incorrect = sum(int(item.get("incorrect_count") or 0) for item in by_decision_type)
            evaluated = correct + incorrect
            success_rate = round((correct / evaluated) * 100, 2) if evaluated else None

            return {
                "status": "OK",
                "summary": {
                    "total_decisions": total_decisions,
                    "evaluated_decisions": evaluated,
                    "success_rate": success_rate,
                    "total_estimated_impact": round(total_estimated, 2),
                    "total_actual_impact": round(total_actual, 2),
                },
                "by_decision_type": by_decision_type,
                "by_recorded_outcome": by_outcome,
            }
        finally:
            db.close()
