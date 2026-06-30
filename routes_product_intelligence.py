"""Business OS v8.7 — Product Intelligence Routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from product_intelligence import ProductIntelligenceEngine

router = APIRouter()


@router.get("/products/diagnostics")
def business_os_products_diagnostics(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return ProductIntelligenceEngine.diagnostics()


@router.get("/products")
def business_os_products(
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    limit: int = 50,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ProductIntelligenceEngine.list_products(window=window, country_code=country_code, profile_id=profile_id, limit=limit)


@router.get("/products/{asin}")
def business_os_product_360(
    asin: str,
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ProductIntelligenceEngine.product_360(asin=asin, window=window, country_code=country_code, profile_id=profile_id)


@router.get("/products/{asin}/360")
def business_os_product_360_alias(
    asin: str,
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ProductIntelligenceEngine.product_360(asin=asin, window=window, country_code=country_code, profile_id=profile_id)


@router.get("/products/{asin}/health")
def business_os_product_health(
    asin: str,
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ProductIntelligenceEngine.product_health(asin=asin, window=window, country_code=country_code, profile_id=profile_id)


@router.get("/products/{asin}/revenue")
def business_os_product_revenue(
    asin: str,
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ProductIntelligenceEngine.product_revenue(asin=asin, window=window, country_code=country_code, profile_id=profile_id)


@router.get("/products/{asin}/profit")
def business_os_product_profit(
    asin: str,
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ProductIntelligenceEngine.product_profit(asin=asin, window=window, country_code=country_code, profile_id=profile_id)


@router.get("/products/{asin}/listing")
def business_os_product_listing(
    asin: str,
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ProductIntelligenceEngine.product_listing(asin=asin, window=window, country_code=country_code, profile_id=profile_id)


@router.get("/products/{asin}/timeline")
def business_os_product_timeline(
    asin: str,
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    limit: int = 50,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ProductIntelligenceEngine.product_timeline(asin=asin, window=window, country_code=country_code, profile_id=profile_id, limit=limit)
