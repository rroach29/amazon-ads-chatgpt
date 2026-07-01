"""Business OS v0.6.4 — Product Metrics routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from business_os.product_metrics.service import ProductMetricsService

router = APIRouter()


@router.get("/product-metrics/{master_product_id}")
def product_metrics(
    master_product_id: str,
    days: int = 30,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ProductMetricsService.product_metrics(master_product_id=master_product_id, days=days)


@router.get("/product-metrics")
def product_metrics_portfolio(
    limit: int = 250,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ProductMetricsService.portfolio_metrics(limit=limit)
