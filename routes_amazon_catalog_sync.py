"""Amazon Catalog/Listings Identity Sync routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from business_os.registry.amazon_catalog_sync import AmazonCatalogSyncService

router = APIRouter()


@router.get("/registry/amazon-catalog/lookup-sku")
def amazon_catalog_lookup_sku(
    sku: str,
    marketplace: str = "US",
    marketplace_id: str | None = None,
    seller_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return AmazonCatalogSyncService.lookup_sku(
        sku=sku,
        marketplace=marketplace,
        marketplace_id=marketplace_id,
        seller_id=seller_id,
    )


@router.post("/registry/amazon-catalog/sync")
def amazon_catalog_sync(
    marketplace: str = "US",
    marketplace_id: str | None = None,
    seller_id: str | None = None,
    dry_run: bool = True,
    limit: int = 50,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return AmazonCatalogSyncService.sync_skus(
        marketplace=marketplace,
        marketplace_id=marketplace_id,
        seller_id=seller_id,
        dry_run=dry_run,
        limit=limit,
    )
