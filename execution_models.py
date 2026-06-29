"""
Business OS v3.4.1
Execution Framework Models

These SQLAlchemy models track approved execution requests and results.

v3.4.1 is framework-only:
- no live Amazon API mutation yet
- safe dry-run execution records
- ready for v3.4.2 live execution handlers
"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, JSON

from database import Base


class ExecutionJob(Base):
    __tablename__ = "execution_jobs"

    id = Column(Integer, primary_key=True, index=True)

    decision_id = Column(Integer, index=True, nullable=True)

    channel = Column(String, index=True, default="amazon_ads")

    profile_id = Column(String, index=True, nullable=True)
    country_code = Column(String, index=True, nullable=True)
    marketplace = Column(String, index=True, nullable=True)
    currency = Column(String, nullable=True)

    action = Column(String, index=True)
    status = Column(String, index=True, default="PENDING")

    dry_run = Column(Boolean, default=True)

    requested_by = Column(String, nullable=True)

    payload = Column(JSON, nullable=True)
    validation_errors = Column(JSON, nullable=True)

    requested_at = Column(DateTime, default=datetime.utcnow)
    approved_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class ExecutionResult(Base):
    __tablename__ = "execution_results"

    id = Column(Integer, primary_key=True, index=True)

    execution_job_id = Column(Integer, index=True)
    decision_id = Column(Integer, index=True, nullable=True)

    success = Column(Boolean, default=False)
    dry_run = Column(Boolean, default=True)

    amazon_request_id = Column(String, nullable=True)
    http_status = Column(Integer, nullable=True)

    action = Column(String, index=True)
    status = Column(String, index=True)

    response_json = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)

    execution_time_ms = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
