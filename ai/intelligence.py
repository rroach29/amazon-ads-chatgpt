from business_context import get_business_os_context
from morning_brief import build_morning_brief
from decision_metrics import get_decision_metrics
from decision_history import get_decision_history


def build_business_intelligence():
    context = get_business_os_context()
    morning = build_morning_brief()
    metrics = get_decision_metrics()
    history = get_decision_history(limit=10)

    return {
        "status": "OK",
        "title": "Business Intelligence",
        "executive_summary": morning.get("executive_summary", {}),
        "morning_brief": morning,
        "business_context": context,
        "decision_metrics": metrics,
        "recent_decisions": history.get("items", []),
    }
