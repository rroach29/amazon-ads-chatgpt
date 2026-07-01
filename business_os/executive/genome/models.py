"""Executive Brain v2.0 — Product Genome database model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Text

from database import Base


class ProductGenome(Base):
    __tablename__ = "product_genomes"

    id = Column(Integer, primary_key=True, index=True)
    master_product_id = Column(String, unique=True, index=True, nullable=False)

    brand = Column(String, index=True, nullable=True)
    product_family = Column(String, index=True, nullable=True)
    primary_sku = Column(String, index=True, nullable=True)
    name = Column(String, nullable=False)

    product_health = Column(Integer, default=0)
    organic_strength = Column(Integer, default=0)
    advertising_dependency_index = Column(Integer, default=0)
    profitability = Column(Integer, default=0)
    growth_momentum = Column(Integer, default=50)
    confidence = Column(Integer, default=50)

    lifecycle_stage = Column(String, index=True, default="Unknown")
    archetype = Column(String, index=True, default="Unclassified")
    objective = Column(String, nullable=True)

    top_opportunity = Column(JSON, nullable=True)
    top_risk = Column(JSON, nullable=True)
    executive_recommendation = Column(JSON, nullable=True)
    evidence = Column(JSON, nullable=True)
    metrics = Column(JSON, nullable=True)

    summary = Column(Text, nullable=True)
    score_version = Column(String, default="executive-brain-2.0")

    calculated_at = Column(DateTime, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
