"""Executive Brain v2.0.1 — Registry Linking routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from business_os.registry.linking.service import RegistryLinkingService

router = APIRouter()


@router.get("/registry/linking/status")
def registry_linking_status(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return RegistryLinkingService.status()


@router.post("/registry/linking/ensure-columns")
def registry_linking_ensure_columns(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return RegistryLinkingService.ensure_columns()


@router.get("/registry/linking/summary")
def registry_linking_summary(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return RegistryLinkingService.summary()


@router.get("/registry/linking/resolve")
def registry_linking_resolve(
    sku: str | None = None,
    asin: str | None = None,
    text_value: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RegistryLinkingService.resolve(sku=sku, asin=asin, text_value=text_value)


@router.post("/registry/linking/link-seller-central")
def registry_link_seller_central(
    dry_run: bool = True,
    limit: int = 10000,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RegistryLinkingService.link_seller_central(dry_run=dry_run, limit=limit)


@router.post("/registry/linking/link-campaign-details")
def registry_link_campaign_details(
    dry_run: bool = True,
    limit: int = 10000,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RegistryLinkingService.link_campaign_details(dry_run=dry_run, limit=limit)


@router.post("/registry/linking/link-search-terms")
def registry_link_search_terms(
    dry_run: bool = True,
    limit: int = 10000,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RegistryLinkingService.link_search_terms(dry_run=dry_run, limit=limit)


@router.post("/registry/linking/link-all")
def registry_link_all(
    dry_run: bool = True,
    limit: int = 10000,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RegistryLinkingService.link_all(dry_run=dry_run, limit=limit)
