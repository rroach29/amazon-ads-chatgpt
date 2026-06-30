from fastapi import APIRouter, Header

from auth import verify_key
from business_data_context import resolve_data_context
from dashboard import (
    get_latest_dashboard,
    get_top_campaigns,
    get_waste_campaigns,
    get_winning_search_terms,
    get_wasted_search_terms,
)
from decision_history import get_decision_history

router = APIRouter()


@router.get("/analytics-health")
def analytics_health(
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)

    context = resolve_data_context(
        window="latest",
        country_code=country_code,
        profile_id=profile_id,
    )

    dashboard = get_latest_dashboard(country_code=country_code, profile_id=profile_id)
    top_campaigns = get_top_campaigns(limit=5, country_code=country_code, profile_id=profile_id)
    waste_campaigns = get_waste_campaigns(min_spend=3, limit=5, country_code=country_code, profile_id=profile_id)
    winning_terms = get_winning_search_terms(max_acos=35, min_orders=1, limit=5, country_code=country_code, profile_id=profile_id)
    wasted_terms = get_wasted_search_terms(min_spend=3, limit=5, country_code=country_code, profile_id=profile_id)
    open_decisions = get_decision_history(status="OPEN", limit=10)

    return {
        "status": "OK",
        "data_context": context,
        "dashboard_date": dashboard.get("date"),
        "detail_query_contexts": {
            "top_campaigns": top_campaigns.get("data_context"),
            "waste_campaigns": waste_campaigns.get("data_context"),
            "winning_search_terms": winning_terms.get("data_context"),
            "wasted_search_terms": wasted_terms.get("data_context"),
            "open_decisions": open_decisions.get("data_context"),
        },
        "counts": {
            "top_campaigns": top_campaigns.get("count"),
            "waste_campaigns": waste_campaigns.get("count"),
            "winning_search_terms": winning_terms.get("count"),
            "wasted_search_terms": wasted_terms.get("count"),
            "open_decisions": open_decisions.get("count"),
        },
        "sample": {
            "top_campaigns": top_campaigns.get("campaigns", [])[:2],
            "waste_campaigns": waste_campaigns.get("campaigns", [])[:2],
            "winning_search_terms": winning_terms.get("search_terms", [])[:2],
            "wasted_search_terms": wasted_terms.get("search_terms", [])[:2],
            "open_decisions": open_decisions.get("items", [])[:2],
        },
    }
