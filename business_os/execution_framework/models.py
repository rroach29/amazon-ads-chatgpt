"""Business OS v0.5.0 — Execution Framework models."""

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.sql import func

from models import Base


class ExecutionPlan(Base):
    __tablename__ = "business_os_execution_plans"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(String, unique=True, index=True, nullable=False)
    decision_id = Column(String, index=True, nullable=False)
    master_product_id = Column(String, index=True, nullable=True)
    product_name = Column(String, nullable=True)

    platform = Column(String, index=True, nullable=False, default="amazon_ads")
    action_type = Column(String, index=True, nullable=False)
    title = Column(String, nullable=False)
    status = Column(String, index=True, nullable=False, default="Planned")

    risk_level = Column(String, nullable=False, default="Low")
    expected_monthly_impact = Column(Float, nullable=True)
    confidence = Column(Integer, nullable=True)
    rollback_available = Column(Boolean, default=False)

    simulation = Column(JSON, nullable=True)
    execution_payload = Column(JSON, nullable=True)
    verification = Column(JSON, nullable=True)

    source_decision = Column(JSON, nullable=True)

    approved_at = Column(DateTime, nullable=True)
    executed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ExecutionStep(Base):
    __tablename__ = "business_os_execution_steps"

    id = Column(Integer, primary_key=True, index=True)
    step_id = Column(String, unique=True, index=True, nullable=False)
    plan_id = Column(String, ForeignKey("business_os_execution_plans.plan_id"), index=True, nullable=False)

    sequence = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    action_type = Column(String, nullable=False)
    status = Column(String, index=True, nullable=False, default="Pending")
    platform = Column(String, nullable=False, default="amazon_ads")

    request_payload = Column(JSON, nullable=True)
    response_payload = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class ExecutionResult(Base):
    __tablename__ = "business_os_execution_results"

    id = Column(Integer, primary_key=True, index=True)
    result_id = Column(String, unique=True, index=True, nullable=False)
    plan_id = Column(String, ForeignKey("business_os_execution_plans.plan_id"), index=True, nullable=False)
    decision_id = Column(String, index=True, nullable=False)

    platform = Column(String, nullable=False, default="amazon_ads")
    action_type = Column(String, nullable=False)
    status = Column(String, index=True, nullable=False)
    success = Column(Boolean, default=False)

    api_request = Column(JSON, nullable=True)
    api_response = Column(JSON, nullable=True)
    verification = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
