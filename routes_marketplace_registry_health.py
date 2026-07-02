"""Marketplace Registry Health routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from business_os.registry.marketplace_health import MarketplaceRegistryHealthService

router = APIRouter()


@router.get("/registry/marketplace-health")
def marketplace_registry_health(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return MarketplaceRegistryHealthService.summary()
