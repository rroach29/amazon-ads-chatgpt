"""Amazon Product Identity Sync routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from business_os.registry.amazon_identity_sync import AmazonIdentitySyncService

router = APIRouter()


@router.get("/registry/amazon-identity/summary")
def amazon_identity_summary(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return AmazonIdentitySyncService.summary()


@router.get("/registry/amazon-identity/seller-central-diagnostics")
def amazon_seller_central_identity_diagnostics(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return AmazonIdentitySyncService.seller_central_diagnostics()


@router.post("/registry/amazon-identity/sync")
def amazon_identity_sync(
    dry_run: bool = True,
    limit: int = 1000,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return AmazonIdentitySyncService.sync_from_seller_central(dry_run=dry_run, limit=limit)
