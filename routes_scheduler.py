from fastapi import APIRouter, Header

from auth import verify_key
from scheduler_tasks import scheduled_amazon_ads_collection, scheduled_dashboard_collection

router = APIRouter()


@router.post("/run")
def run_scheduler_now(x_api_key: str = Header(...)):
    verify_key(x_api_key)

    result = scheduled_amazon_ads_collection()

    return result


@router.post("/collect")
def run_dashboard_collection_now(x_api_key: str = Header(...)):
    verify_key(x_api_key)

    result = scheduled_dashboard_collection()

    return {
        "status": "OK",
        "message": "Dashboard collection scheduler executed.",
        "result": result,
    }
