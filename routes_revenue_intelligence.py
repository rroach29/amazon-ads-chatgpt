"""Business OS v8.6/v9.0 — Revenue Intelligence Routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from revenue import RevenueIntelligenceEngine, RevenueReconciliationService

router = APIRouter()


@router.get("/revenue/diagnostics")
def business_os_revenue_diagnostics(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return RevenueIntelligenceEngine.diagnostics()


@router.get("/revenue/sp-api/status")
def business_os_revenue_sp_api_status(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return RevenueIntelligenceEngine.sp_api_status()


@router.get("/revenue/summary")
def business_os_revenue_summary(
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RevenueIntelligenceEngine.summary(window=window, country_code=country_code, profile_id=profile_id)


@router.get("/revenue/marketplaces")
def business_os_revenue_marketplaces(
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RevenueIntelligenceEngine.marketplaces(window=window, country_code=country_code, profile_id=profile_id)


@router.get("/revenue/products")
def business_os_revenue_products(
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    limit: int = 50,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RevenueIntelligenceEngine.products(window=window, country_code=country_code, profile_id=profile_id, limit=limit)


@router.get("/revenue/paid-vs-organic")
def business_os_revenue_paid_vs_organic(
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RevenueIntelligenceEngine.paid_vs_organic(window=window, country_code=country_code, profile_id=profile_id)


# v9.0 first-class reconciliation endpoints.
@router.get("/revenue/organic-vs-paid")
def business_os_revenue_organic_vs_paid(
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RevenueReconciliationService.organic_vs_paid(window=window, country_code=country_code, profile_id=profile_id)


@router.get("/revenue/reconciliation")
def business_os_revenue_reconciliation(
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RevenueReconciliationService.organic_vs_paid(window=window, country_code=country_code, profile_id=profile_id)


@router.get("/revenue/executive-snapshot")
def business_os_revenue_executive_snapshot(
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RevenueReconciliationService.executive_snapshot(window=window, country_code=country_code, profile_id=profile_id)
