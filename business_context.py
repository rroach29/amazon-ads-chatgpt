from dashboard import (
    get_latest_dashboard,
    get_dashboard_history,
    get_campaigns,
    get_top_campaigns,
    get_waste_campaigns,
    get_search_terms,
    get_winning_search_terms,
    get_wasted_search_terms,
)

from recommendations import build_recommendations
from optimization_queue import get_queue


def get_business_os_context():
    return {
        "status": "OK",
        "dashboard": get_latest_dashboard(),
        "history": get_dashboard_history(days=30),
        "campaigns": get_campaigns(limit=100),
        "top_campaigns": get_top_campaigns(limit=25),
        "waste_campaigns": get_waste_campaigns(min_spend=10, limit=25),
        "search_terms": get_search_terms(limit=100),
        "winning_search_terms": get_winning_search_terms(
            max_acos=35,
            min_orders=1,
            limit=25,
        ),
        "wasted_search_terms": get_wasted_search_terms(
            min_spend=10,
            limit=25,
        ),
        "recommendations": build_recommendations(),
        "optimization_queue": get_queue(status="PENDING", limit=100),
    }
