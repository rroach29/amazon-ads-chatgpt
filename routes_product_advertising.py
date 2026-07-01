"""Business OS v0.4.0 — Product Advertising Intelligence routes."""
from fastapi import APIRouter, Header
from auth import verify_key
from business_os.products.advertising.service import ProductAdvertisingIntelligenceService
router = APIRouter()

@router.get("/products/advertising/summary")
def product_advertising_summary(limit: int = 100, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return ProductAdvertisingIntelligenceService.summary(limit=limit)

@router.get("/products/{master_product_id}/advertising")
def product_advertising_detail(master_product_id: str, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return ProductAdvertisingIntelligenceService.product_advertising(master_product_id)

@router.post("/products/advertising/generate-mission-control")
def product_advertising_generate_mission_control(limit: int = 250, replace_existing_product_ad_decisions: bool = True, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return ProductAdvertisingIntelligenceService.generate_mission_control_decisions(limit=limit, replace_existing_product_ad_decisions=replace_existing_product_ad_decisions)
