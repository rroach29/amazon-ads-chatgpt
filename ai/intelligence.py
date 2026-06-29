from business_context import get_business_os_context
from morning_brief import build_morning_brief
from decision_metrics import get_decision_metrics
from decision_history import get_decision_history
from marketplace_summary import build_marketplace_summary, compare_marketplaces


def build_business_intelligence(country_code=None, profile_id=None, compare_to="US"):
    context = get_business_os_context()
    morning = build_morning_brief(
        country_code=country_code,
        profile_id=profile_id,
        compare_to=compare_to,
    )
    metrics = get_decision_metrics()
    history = get_decision_history(limit=10)
    marketplace_summary = build_marketplace_summary()

    marketplace_comparison = None
    if country_code and compare_to:
        marketplace_comparison = compare_marketplaces(
            primary_country_code=country_code,
            comparison_country_code=compare_to,
        )

    return {
        "status": "OK",
        "title": "Business Intelligence",
        "marketplace_summary": marketplace_summary,
        "marketplace_comparison": marketplace_comparison,
        "executive_summary": morning.get("executive_summary", {}),
        "morning_brief": morning,
        "business_context": context,
        "decision_metrics": metrics,
        "recent_decisions": history.get("items", []),
    }
