from fastapi import APIRouter, Header

from auth import verify_key
from knowledge_graph import RelationshipService, ProductIntelligenceService

router = APIRouter()


@router.get("/knowledge-graph")
def business_os_knowledge_graph(
    country_code: str | None = None,
    profile_id: str | None = None,
    limit: int = 250,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RelationshipService.build_graph(
        country_code=country_code,
        profile_id=profile_id,
        limit=limit,
    )


@router.get("/knowledge-graph/campaigns/{campaign_id}")
def business_os_campaign_context(
    campaign_id: str,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RelationshipService.campaign_context(campaign_id=campaign_id)


@router.get("/knowledge-graph/search-terms/{search_term}")
def business_os_search_term_context(
    search_term: str,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RelationshipService.search_term_context(search_term=search_term)


@router.get("/product-intelligence")
def business_os_product_intelligence(
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ProductIntelligenceService.product_summary(
        country_code=country_code,
        profile_id=profile_id,
    )
