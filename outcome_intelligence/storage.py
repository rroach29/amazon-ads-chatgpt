"""
Business OS v6.3
Outcome Intelligence Storage

Creates lightweight generic tables used by the learning loop. The create calls
are idempotent and safe to run from Swagger endpoints.
"""

from sqlalchemy import text

CREATE_DECISION_OUTCOMES_SQL = """
CREATE TABLE IF NOT EXISTS decision_outcomes (
    id SERIAL PRIMARY KEY,
    decision_history_id INTEGER,
    decision_type VARCHAR(100),
    optimizer_name VARCHAR(100),
    estimated_impact DOUBLE PRECISION DEFAULT 0,
    actual_impact DOUBLE PRECISION,
    variance DOUBLE PRECISION,
    variance_percent DOUBLE PRECISION,
    outcome_status VARCHAR(50),
    evaluation_period_days INTEGER DEFAULT 14,
    measured_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    notes TEXT,
    raw JSONB
);
"""

CREATE_LEARNING_EVENTS_SQL = """
CREATE TABLE IF NOT EXISTS learning_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(100),
    decision_history_id INTEGER,
    decision_type VARCHAR(100),
    optimizer_name VARCHAR(100),
    confidence_before DOUBLE PRECISION,
    confidence_after DOUBLE PRECISION,
    accuracy_percent DOUBLE PRECISION,
    message TEXT,
    payload JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
"""

CREATE_CONFIDENCE_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS confidence_history (
    id SERIAL PRIMARY KEY,
    decision_type VARCHAR(100),
    optimizer_name VARCHAR(100),
    confidence_before DOUBLE PRECISION,
    confidence_after DOUBLE PRECISION,
    accuracy_percent DOUBLE PRECISION,
    sample_size INTEGER DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
"""

CREATE_OPTIMIZER_METRICS_SQL = """
CREATE TABLE IF NOT EXISTS optimizer_metrics (
    id SERIAL PRIMARY KEY,
    optimizer_name VARCHAR(100),
    decision_type VARCHAR(100),
    opportunities_found INTEGER DEFAULT 0,
    decisions_executed INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    estimated_impact DOUBLE PRECISION DEFAULT 0,
    actual_impact DOUBLE PRECISION DEFAULT 0,
    avg_accuracy DOUBLE PRECISION,
    avg_confidence DOUBLE PRECISION,
    calculated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
"""


def ensure_outcome_tables(db):
    db.execute(text(CREATE_DECISION_OUTCOMES_SQL))
    db.execute(text(CREATE_LEARNING_EVENTS_SQL))
    db.execute(text(CREATE_CONFIDENCE_HISTORY_SQL))
    db.execute(text(CREATE_OPTIMIZER_METRICS_SQL))
    db.commit()
