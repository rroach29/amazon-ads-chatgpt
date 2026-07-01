"""Business Registry v1.3 — Registry Manager schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MasterProductCreate(BaseModel):
    brand: str | None = None
    product_family: str | None = None
    primary_sku: str | None = None
    ean_upc: str | None = None
    name: str = Field(..., min_length=1)
    status: str = "Active"
    lifecycle_stage: str = "Unassigned"
    primary_channel_strategy: str | None = None
    notes: str | None = None


class MasterProductUpdate(BaseModel):
    brand: str | None = None
    product_family: str | None = None
    primary_sku: str | None = None
    ean_upc: str | None = None
    name: str | None = None
    status: str | None = None
    lifecycle_stage: str | None = None
    primary_channel_strategy: str | None = None
    notes: str | None = None
    active: bool | None = None


class ChannelMappingCreate(BaseModel):
    master_product_id: str
    brand: str | None = None
    primary_sku: str | None = None
    channel: str
    marketplace: str | None = None
    currency: str | None = None
    channel_product_id: str | None = None
    channel_listing_id: str | None = None
    asin: str | None = None
    sku: str | None = None
    status: str = "Needs Mapping"
    notes: str | None = None
    raw: dict[str, Any] | None = None


class ChannelMappingUpdate(BaseModel):
    brand: str | None = None
    primary_sku: str | None = None
    channel: str | None = None
    marketplace: str | None = None
    currency: str | None = None
    channel_product_id: str | None = None
    channel_listing_id: str | None = None
    asin: str | None = None
    sku: str | None = None
    status: str | None = None
    notes: str | None = None
    raw: dict[str, Any] | None = None
