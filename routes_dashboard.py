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

@router.get("/campaigns")
def dashboard_campaigns(limit: int = 100, db: Session = Depends(get_db)):
    return get_campaigns(db, limit)


@router.get("/campaigns/top")
def dashboard_top_campaigns(limit: int = 25, db: Session = Depends(get_db)):
    return get_top_campaigns(db, limit)


@router.get("/campaigns/waste")
def dashboard_waste_campaigns(
    min_spend: float = 10,
    limit: int = 25,
    db: Session = Depends(get_db)
):
    return get_waste_campaigns(db, min_spend, limit)


@router.get("/search-terms")
def dashboard_search_terms(limit: int = 100, db: Session = Depends(get_db)):
    return get_search_terms(db, limit)


@router.get("/search-terms/winners")
def dashboard_search_term_winners(
    max_acos: float = 35,
    min_orders: int = 1,
    limit: int = 25,
    db: Session = Depends(get_db)
):
    return get_winning_search_terms(db, max_acos, min_orders, limit)


@router.get("/search-terms/waste")
def dashboard_search_term_waste(
    min_spend: float = 10,
    limit: int = 25,
    db: Session = Depends(get_db)
):
    return get_wasted_search_terms(db, min_spend, limit)
