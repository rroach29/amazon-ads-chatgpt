"""Business Core v1.1.1 — Registry Integration routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from business_registry.resolver import RegistryResolverService

router = APIRouter()


@router.get("/registry/integration/status")
def registry_integration_status(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return RegistryResolverService.migration_status()


@router.post("/registry/integration/ensure-columns")
def registry_integration_ensure_columns(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return RegistryResolverService.ensure_registry_columns()


@router.get("/registry/integration/summary")
def registry_integration_summary(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return RegistryResolverService.integration_summary()


@router.get("/registry/integration/resolve")
def registry_integration_resolve(
    sku: str | None = None,
    asin: str | None = None,
    channel: str | None = None,
    channel_product_id: str | None = None,
    channel_listing_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RegistryResolverService.resolve_identifier(
        sku=sku,
        asin=asin,
        channel=channel,
        channel_product_id=channel_product_id,
        channel_listing_id=channel_listing_id,
    )


@router.post("/registry/integration/backfill-seller-central")
def registry_backfill_seller_central(
    dry_run: bool = True,
    limit: int = 5000,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RegistryResolverService.backfill_seller_central(dry_run=dry_run, limit=limit)


@router.post("/registry/integration/backfill-campaign-details")
def registry_backfill_campaign_details(
    dry_run: bool = True,
    limit: int = 5000,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RegistryResolverService.backfill_campaign_details(dry_run=dry_run, limit=limit)


@router.post("/registry/integration/backfill-search-terms")
def registry_backfill_search_terms(
    dry_run: bool = True,
    limit: int = 5000,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RegistryResolverService.backfill_search_terms(dry_run=dry_run, limit=limit)
