from fastapi import APIRouter, Header

from auth import verify_key
from scheduler_tasks import scheduled_amazon_ads_collection, scheduled_dashboard_collection

router = APIRouter()


@router.post("/scheduler/run")
def run_scheduler_now(x_api_key: str = Header(...)):
    verify_key(x_api_key)

    scheduled_amazon_ads_collection()

    return {
        "status": "OK",
        "message": "Report creation scheduler executed."
    }


@router.post("/scheduler/collect")
def run_dashboard_collection_now(x_api_key: str = Header(...)):
    verify_key(x_api_key)

    scheduled_dashboard_collection()

    return {
        "status": "OK",
        "message": "Dashboard collection scheduler executed."
    }
