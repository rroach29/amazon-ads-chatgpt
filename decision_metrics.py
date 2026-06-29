from database import SessionLocal
from models import DecisionHistory


def get_decision_metrics():
    db = SessionLocal()

    try:
        rows = (
            db.query(DecisionHistory)
            .filter(DecisionHistory.channel == "amazon_ads")
            .all()
        )

        total = len(rows)
        evaluated = [r for r in rows if r.status == "EVALUATED"]
        open_items = [r for r in rows if r.status == "OPEN"]
        correct = [r for r in evaluated if r.was_correct is True]

        total_estimated_impact = sum((r.estimated_monthly_impact or 0) for r in rows)
        total_actual_impact = sum((r.actual_impact or 0) for r in evaluated)

        avg_confidence = (
            round(sum((r.confidence or 0) for r in rows) / total, 2)
            if total
            else 0
        )

        accuracy = (
            round((len(correct) / len(evaluated)) * 100, 2)
            if evaluated
            else None
        )

        by_type = {}

        for r in rows:
            decision_type = r.decision or "UNKNOWN"

            if decision_type not in by_type:
                by_type[decision_type] = {
                    "total": 0,
                    "open": 0,
                    "evaluated": 0,
                    "correct": 0,
                    "accuracy": None,
                    "estimated_impact": 0,
                    "actual_impact": 0,
                    "average_confidence": 0,
                    "_confidence_sum": 0,
                }

            item = by_type[decision_type]
            item["total"] += 1
            item["estimated_impact"] += r.estimated_monthly_impact or 0
            item["_confidence_sum"] += r.confidence or 0

            if r.status == "OPEN":
                item["open"] += 1

            if r.status == "EVALUATED":
                item["evaluated"] += 1
                item["actual_impact"] += r.actual_impact or 0

                if r.was_correct is True:
                    item["correct"] += 1

        for item in by_type.values():
            item["average_confidence"] = (
                round(item["_confidence_sum"] / item["total"], 2)
                if item["total"]
                else 0
            )

            item["accuracy"] = (
                round((item["correct"] / item["evaluated"]) * 100, 2)
                if item["evaluated"]
                else None
            )

            item["estimated_impact"] = round(item["estimated_impact"], 2)
            item["actual_impact"] = round(item["actual_impact"], 2)

            del item["_confidence_sum"]

        best_type = None
        worst_type = None

        evaluated_types = {
            key: value
            for key, value in by_type.items()
            if value["accuracy"] is not None
        }

        if evaluated_types:
            best_type = max(
                evaluated_types.items(),
                key=lambda x: x[1]["accuracy"],
            )[0]

            worst_type = min(
                evaluated_types.items(),
                key=lambda x: x[1]["accuracy"],
            )[0]

        return {
            "status": "OK",
            "total_decisions": total,
            "open_decisions": len(open_items),
            "evaluated_decisions": len(evaluated),
            "correct_decisions": len(correct),
            "accuracy": accuracy,
            "average_confidence": avg_confidence,
            "estimated_monthly_impact": round(total_estimated_impact, 2),
            "actual_impact": round(total_actual_impact, 2),
            "best_decision_type": best_type,
            "worst_decision_type": worst_type,
            "by_type": by_type,
        }

    finally:
        db.close()
