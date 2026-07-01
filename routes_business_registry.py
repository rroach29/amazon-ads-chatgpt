"""Business Core v1.0 — Business Registry routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header

from auth import verify_key
from business_registry.service import BusinessRegistryService

router = APIRouter()


@router.get("/registry/health")
def business_registry_health(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return BusinessRegistryService.health()


@router.post("/registry/seed-master-products")
def seed_master_products(
    overwrite: bool = False,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return BusinessRegistryService.seed_master_products(overwrite=overwrite)


@router.get("/registry/master-products")
def list_master_products(
    brand: str | None = None,
    product_family: str | None = None,
    status: str | None = None,
    limit: int = 250,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return BusinessRegistryService.list_master_products(
        brand=brand,
        product_family=product_family,
        status=status,
        limit=limit,
    )


@router.get("/registry/master-products/{master_product_id}")
def get_master_product(
    master_product_id: str,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return BusinessRegistryService.get_master_product(master_product_id=master_product_id)


@router.get("/registry/product-channels")
def list_product_channels(
    master_product_id: str | None = None,
    channel: str | None = None,
    status: str | None = None,
    limit: int = 500,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return BusinessRegistryService.list_channels(
        master_product_id=master_product_id,
        channel=channel,
        status=status,
        limit=limit,
    )


@router.get("/registry/resolve")
def resolve_business_object(
    sku: str | None = None,
    asin: str | None = None,
    channel: str | None = None,
    channel_product_id: str | None = None,
    channel_listing_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return BusinessRegistryService.resolve(
        sku=sku,
        asin=asin,
        channel=channel,
        channel_product_id=channel_product_id,
        channel_listing_id=channel_listing_id,
    )


@router.get("/registry/events")
def list_business_events(
    master_product_id: str | None = None,
    event_type: str | None = None,
    limit: int = 100,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return BusinessRegistryService.events(
        master_product_id=master_product_id,
        event_type=event_type,
        limit=limit,
    )


@router.post("/registry/events")
def create_business_event(
    event_type: str,
    title: str,
    master_product_id: str | None = None,
    channel: str | None = None,
    description: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return BusinessRegistryService.create_event(
        event_type=event_type,
        title=title,
        master_product_id=master_product_id,
        channel=channel,
        description=description,
        source="swagger",
        payload={},
    )
