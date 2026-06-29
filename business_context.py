from dashboard import (
    get_latest_dashboard,
    get_dashboard_history,
    get_top_campaigns,
    get_waste_campaigns,
    get_winning_search_terms,
    get_wasted_search_terms,
)

from recommendations import build_recommendations
from optimization_queue import get_queue
from decision_history import get_decision_history

def trim_list(section, key, max_items):
    if not isinstance(section, dict):
        return section

    items = section.get(key, [])

    if not isinstance(items, list):
        return section

    section[key] = items[:max_items]
    section["returned_count"] = len(section[key])
    return section


def get_business_os_context():
    history = get_dashboard_history(days=14)

    return {
        "status": "OK",
        "dashboard": get_latest_dashboard(),

        "history": history,

        "top_campaigns": trim_list(
            get_top_campaigns(limit=10),
            "campaigns",
            10,
        ),

        "waste_campaigns": trim_list(
            get_waste_campaigns(min_spend=10, limit=10),
            "campaigns",
            10,
        ),

        "winning_search_terms": trim_list(
            get_winning_search_terms(max_acos=35, min_orders=1, limit=10),
            "search_terms",
            10,
        ),

        "wasted_search_terms": trim_list(
            get_wasted_search_terms(min_spend=10, limit=10),
            "search_terms",
            10,
        ),

        "recommendations": trim_list(
            build_recommendations(),
            "recommendations",
            15,
        ),

        "optimization_queue": trim_list(
            get_queue(status="PENDING", limit=15),
            "items",
            15,
        ),
    }
