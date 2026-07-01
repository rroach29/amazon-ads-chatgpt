"""Business Core v1.0 — Business Registry SQLAlchemy models.

This is the canonical identity layer for the Business OS.
Everything eventually resolves to a Master Product ID.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Text, Boolean

from database import Base


class MasterProduct(Base):
    __tablename__ = "master_products"

    id = Column(Integer, primary_key=True, index=True)
    master_product_id = Column(String, unique=True, index=True, nullable=False)

    brand = Column(String, index=True, nullable=True)
    product_family = Column(String, index=True, nullable=True)
    primary_sku = Column(String, index=True, nullable=True)
    ean_upc = Column(String, index=True, nullable=True)

    name = Column(String, index=True, nullable=False)
    status = Column(String, index=True, default="Active")
    lifecycle_stage = Column(String, index=True, default="Unassigned")
    primary_channel_strategy = Column(String, nullable=True)

    notes = Column(Text, nullable=True)
    source = Column(String, nullable=True)
    raw = Column(JSON, nullable=True)

    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class ProductChannel(Base):
    __tablename__ = "product_channels"

    id = Column(Integer, primary_key=True, index=True)
    master_product_id = Column(String, index=True, nullable=False)

    brand = Column(String, index=True, nullable=True)
    primary_sku = Column(String, index=True, nullable=True)

    channel = Column(String, index=True, nullable=False)
    marketplace = Column(String, index=True, nullable=True)
    currency = Column(String, nullable=True)

    channel_product_id = Column(String, index=True, nullable=True)
    channel_listing_id = Column(String, index=True, nullable=True)
    asin = Column(String, index=True, nullable=True)
    sku = Column(String, index=True, nullable=True)

    status = Column(String, index=True, default="Needs Mapping")
    notes = Column(Text, nullable=True)
    raw = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class BusinessEvent(Base):
    __tablename__ = "business_events"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String, unique=True, index=True, nullable=False)

    event_type = Column(String, index=True, nullable=False)
    occurred_at = Column(DateTime, default=datetime.utcnow, index=True)

    master_product_id = Column(String, index=True, nullable=True)
    channel = Column(String, index=True, nullable=True)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    source = Column(String, nullable=True)
    payload = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class ProductScore(Base):
    __tablename__ = "product_scores"

    id = Column(Integer, primary_key=True, index=True)
    master_product_id = Column(String, index=True, nullable=False)

    product_health = Column(Integer, default=0)
    organic_strength = Column(Integer, default=0)
    advertising_dependency_index = Column(Integer, default=0)
    profitability = Column(Integer, default=0)
    confidence = Column(Integer, default=0)

    score_version = Column(String, default="business-core-1.0")
    payload = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
