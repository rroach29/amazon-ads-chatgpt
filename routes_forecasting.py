from fastapi import APIRouter, Header

from auth import verify_key
from forecasting.engine import forecast_open_decisions

router = APIRouter()


@router.get("/forecast")
def get_business_os_forecast(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return forecast_open_decisions()


@router.get("/business-score")
def get_business_os_business_score(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    forecast = forecast_open_decisions()
    return {
        "status": "OK",
        "business_score": forecast.get("business_score"),
        "recommendation": forecast.get("recommendation"),
    }
