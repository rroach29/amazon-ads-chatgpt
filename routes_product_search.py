from fastapi import APIRouter, Header
from auth import verify_key
from business_os.products.search.service import ProductSearchIntelligenceService
router = APIRouter()
@router.get('/products/search/summary')
def product_search_summary(limit: int = 250, x_api_key: str = Header(...)):
    verify_key(x_api_key); return ProductSearchIntelligenceService.summary(limit=limit)
@router.get('/products/{master_product_id}/search')
def product_search_detail(master_product_id: str, x_api_key: str = Header(...)):
    verify_key(x_api_key); return ProductSearchIntelligenceService.product_search(master_product_id)
@router.post('/products/search/generate-mission-control')
def product_search_generate_mission_control(limit: int = 250, replace_existing_product_search_decisions: bool = True, x_api_key: str = Header(...)):
    verify_key(x_api_key); return ProductSearchIntelligenceService.generate_mission_control_decisions(limit=limit, replace_existing_product_search_decisions=replace_existing_product_search_decisions)
