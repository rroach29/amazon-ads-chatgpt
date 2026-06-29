from learning.metrics import get_learning_summary


def build_learning_intelligence():
    summary = get_learning_summary()
    by_type = summary.get("by_decision_type", []) or []

    best = None
    worst = None

    if by_type:
        ranked = sorted(
            by_type,
            key=lambda item: float(item.get("avg_accuracy") or 0),
            reverse=True,
        )
        best = ranked[0]
        worst = ranked[-1]

    return {
        "status": "OK",
        "learning_summary": summary,
        "best_decision_type": best,
        "worst_decision_type": worst,
        "narrative": build_learning_narrative(summary, best, worst),
    }


def build_learning_narrative(summary, best, worst):
    total = summary.get("total_records") or 0
    accuracy = summary.get("overall_accuracy")

    if not total:
        return "No learning records exist yet. Evaluate executed decisions to begin building historical confidence."

    message = f"Business OS has {total} learning records"

    if accuracy is not None:
        message += f" with an overall decision accuracy of {accuracy:.1f}%."
    else:
        message += "."

    if best:
        message += f" Best-performing decision type so far: {best.get('decision_type')}."

    if worst and best and worst.get("decision_type") != best.get("decision_type"):
        message += f" Weakest-performing decision type so far: {worst.get('decision_type')}."

    return message
