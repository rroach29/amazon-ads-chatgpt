"""Business OS v0.3.0 — Mission Control models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, JSON, String, Text

from database import Base


class MissionControlDecision(Base):
    __tablename__ = "mission_control_decisions"

    id = Column(Integer, primary_key=True, index=True)
    decision_id = Column(String, unique=True, index=True, nullable=False)

    master_product_id = Column(String, index=True, nullable=True)
    product_name = Column(String, nullable=True)

    title = Column(String, nullable=False)
    category = Column(String, index=True, default="General")
    priority = Column(String, index=True, default="MEDIUM")
    status = Column(String, index=True, default="Pending")

    estimated_monthly_impact = Column(Float, default=0)
    confidence = Column(Integer, default=50)
    reversibility = Column(String, default="Medium")
    urgency = Column(Integer, default=50)

    recommendation = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)
    why_now = Column(Text, nullable=True)
    if_you_do = Column(Text, nullable=True)
    if_you_do_not = Column(Text, nullable=True)

    evidence = Column(JSON, nullable=True)
    actions = Column(JSON, nullable=True)
    source = Column(String, default="mission_control_engine")
    payload = Column(JSON, nullable=True)

    approved = Column(Boolean, default=False)
    approved_at = Column(DateTime, nullable=True)
    dismissed_at = Column(DateTime, nullable=True)
    deferred_until = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow)


class BusinessObjective(Base):
    __tablename__ = "business_objectives"

    id = Column(Integer, primary_key=True, index=True)
    objective_id = Column(String, unique=True, index=True, nullable=False)

    scope = Column(String, index=True, default="business")  # business/product/channel
    master_product_id = Column(String, index=True, nullable=True)

    title = Column(String, nullable=False)
    objective_type = Column(String, index=True, default="Maximize Profit")
    portfolio_strategy = Column(String, index=True, default="Grow")
    status = Column(String, index=True, default="Active")

    target_metric = Column(String, nullable=True)
    target_value = Column(Float, nullable=True)
    current_value = Column(Float, nullable=True)

    notes = Column(Text, nullable=True)
    payload = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
