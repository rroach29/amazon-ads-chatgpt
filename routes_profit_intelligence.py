"""Business OS v8.5 — Profit Intelligence Routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from profit_intelligence import ProfitIntelligenceEngine

router = APIRouter()


@router.get("/profit/diagnostics")
def business_os_profit_diagnostics(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return ProfitIntelligenceEngine.diagnostics()


@router.get("/profit/assumptions")
def business_os_profit_assumptions(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return ProfitIntelligenceEngine.assumptions()


@router.get("/profit/summary")
def business_os_profit_summary(
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ProfitIntelligenceEngine.executive_summary(window=window, country_code=country_code, profile_id=profile_id)


@router.get("/profit/marketplaces")
def business_os_profit_marketplaces(
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ProfitIntelligenceEngine.marketplace_summary(window=window, country_code=country_code, profile_id=profile_id)


@router.get("/profit/campaigns")
def business_os_profit_campaigns(
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    limit: int = 50,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ProfitIntelligenceEngine.campaign_profit(window=window, country_code=country_code, profile_id=profile_id, limit=limit)
