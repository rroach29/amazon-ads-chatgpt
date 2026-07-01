"""Business OS Revenue Intelligence Routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from revenue import RevenueIntelligenceEngine, RevenueReconciliationService
from revenue.debug_tools import SellerCentralDebugService

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
    return RevenueReconciliationService.organic_vs_paid(window=window, country_code=country_code, profile_id=profile_id)


@router.get("/revenue/organic-vs-paid")
def business_os_revenue_organic_vs_paid(
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    debug: bool = False,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RevenueReconciliationService.organic_vs_paid(window=window, country_code=country_code, profile_id=profile_id, debug=debug)


@router.get("/revenue/reconciliation")
def business_os_revenue_reconciliation(
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    debug: bool = False,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RevenueReconciliationService.organic_vs_paid(window=window, country_code=country_code, profile_id=profile_id, debug=debug)


@router.get("/revenue/executive-snapshot")
def business_os_revenue_executive_snapshot(
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RevenueReconciliationService.executive_snapshot(window=window, country_code=country_code, profile_id=profile_id)


@router.get("/revenue/data-health")
def business_os_revenue_data_health(
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RevenueReconciliationService.data_health(country_code=country_code, profile_id=profile_id)


# v9.0.6 Swagger-accessible Seller Central database debug/cleanup actions.
@router.get("/revenue/debug/seller-central-rows")
def business_os_debug_seller_central_rows(
    date: str,
    country_code: str | None = None,
    limit: int = 500,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return SellerCentralDebugService.rows(date_value=date, country_code=country_code, limit=limit)


@router.get("/revenue/debug/seller-central-duplicates")
def business_os_debug_seller_central_duplicates(
    date: str,
    country_code: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return SellerCentralDebugService.duplicates(date_value=date, country_code=country_code)


@router.get("/revenue/debug/seller-central-aggregate-rows")
def business_os_debug_seller_central_aggregate_rows(
    date: str,
    country_code: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return SellerCentralDebugService.aggregate_rows(date_value=date, country_code=country_code)


@router.post("/revenue/cleanup/seller-central-duplicates")
def business_os_cleanup_seller_central_duplicates(
    date: str,
    country_code: str | None = None,
    dry_run: bool = True,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return SellerCentralDebugService.cleanup_duplicates(date_value=date, country_code=country_code, dry_run=dry_run)


@router.post("/revenue/cleanup/seller-central-aggregate-rows")
def business_os_cleanup_seller_central_aggregate_rows(
    date: str,
    country_code: str | None = None,
    dry_run: bool = True,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return SellerCentralDebugService.cleanup_aggregate_rows(date_value=date, country_code=country_code, dry_run=dry_run)
