from fastapi import APIRouter, Header

from auth import verify_key
from forecasting.engine import forecast_open_decisions
from marketplace_summary import build_marketplace_summary

router = APIRouter()


@router.get("/forecast")
def get_business_os_forecast(
    include_marketplace_summary: bool = True,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    forecast = forecast_open_decisions()

    if include_marketplace_summary and isinstance(forecast, dict):
        forecast["marketplace_summary"] = build_marketplace_summary()

    return forecast


@router.get("/business-score")
def get_business_os_business_score(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    forecast = forecast_open_decisions()
    marketplace_summary = build_marketplace_summary()

    return {
        "status": "OK",
        "business_score": forecast.get("business_score"),
        "recommendation": forecast.get("recommendation"),
        "marketplace_summary": marketplace_summary,
    }
