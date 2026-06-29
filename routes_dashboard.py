from fastapi import APIRouter, Header

from auth import verify_key
from dashboard import (
    get_latest_dashboard,
    save_dashboard_from_reports,
    get_dashboard_history,
    get_campaigns,
    get_top_campaigns,
    get_waste_campaigns,
    get_search_terms,
    get_winning_search_terms,
    get_wasted_search_terms,
)

router = APIRouter()


@router.get("")
def dashboard(
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return get_latest_dashboard(country_code=country_code, profile_id=profile_id)


@router.post("/collect/{campaign_report_id}/{search_term_report_id}")
def collect_dashboard(
    campaign_report_id: str,
    search_term_report_id: str,
    country_code: str | None = None,
    profile_id: str | None = None,
    marketplace: str | None = None,
    currency: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return save_dashboard_from_reports(
        campaign_report_id,
        search_term_report_id,
        profile_id=profile_id,
        country_code=country_code,
        marketplace=marketplace,
        currency=currency,
    )


@router.get("/history")
def dashboard_history(
    days: int = 30,
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return get_dashboard_history(days, country_code=country_code, profile_id=profile_id)


@router.get("/campaigns")
def dashboard_campaigns(
    limit: int = 100,
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return get_campaigns(limit, country_code=country_code, profile_id=profile_id)


@router.get("/campaigns/top")
def dashboard_top_campaigns(
    limit: int = 25,
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return get_top_campaigns(limit, country_code=country_code, profile_id=profile_id)


@router.get("/campaigns/waste")
def dashboard_waste_campaigns(
    min_spend: float = 10,
    limit: int = 25,
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return get_waste_campaigns(min_spend, limit, country_code=country_code, profile_id=profile_id)


@router.get("/search-terms")
def dashboard_search_terms(
    limit: int = 100,
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return get_search_terms(limit, country_code=country_code, profile_id=profile_id)


@router.get("/search-terms/winners")
def dashboard_search_term_winners(
    max_acos: float = 35,
    min_orders: int = 1,
    limit: int = 25,
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return get_winning_search_terms(
        max_acos,
        min_orders,
        limit,
        country_code=country_code,
        profile_id=profile_id,
    )


@router.get("/search-terms/waste")
def dashboard_search_term_waste(
    min_spend: float = 10,
    limit: int = 25,
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return get_wasted_search_terms(
        min_spend,
        limit,
        country_code=country_code,
        profile_id=profile_id,
    )
