from fastapi import APIRouter, Header

from auth import verify_key
from dashboard import get_latest_dashboard, save_dashboard_from_reports, get_dashboard_history
router = APIRouter()


@router.get("/dashboard")
def dashboard(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return get_latest_dashboard()


@router.post("/dashboard/collect/{campaign_report_id}/{search_term_report_id}")
def collect_dashboard(
    campaign_report_id: str,
    search_term_report_id: str,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return save_dashboard_from_reports(campaign_report_id, search_term_report_id)

@router.get("/dashboard/history")
def dashboard_history(days: int = 30, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return get_dashboard_history(days)
