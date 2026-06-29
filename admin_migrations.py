from datetime import datetime
from sqlalchemy import text

from database import SessionLocal


CREATE_SCHEMA_MIGRATIONS_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id SERIAL PRIMARY KEY,
    version VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'APPLIED',
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    details JSONB
);
"""


MIGRATION_V3_4_1_SQL = """
CREATE TABLE IF NOT EXISTS execution_jobs (
    id SERIAL PRIMARY KEY,
    decision_id INTEGER,
    channel VARCHAR(100) DEFAULT 'amazon_ads',
    profile_id VARCHAR(100),
    country_code VARCHAR(10),
    marketplace VARCHAR(100),
    currency VARCHAR(10),
    action VARCHAR(100),
    status VARCHAR(50) DEFAULT 'PENDING',
    dry_run BOOLEAN DEFAULT TRUE,
    requested_by VARCHAR(100),
    payload JSONB,
    validation_errors JSONB,
    requested_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    approved_at TIMESTAMP WITHOUT TIME ZONE,
    started_at TIMESTAMP WITHOUT TIME ZONE,
    completed_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS execution_results (
    id SERIAL PRIMARY KEY,
    execution_job_id INTEGER,
    decision_id INTEGER,
    success BOOLEAN DEFAULT FALSE,
    dry_run BOOLEAN DEFAULT TRUE,
    amazon_request_id VARCHAR(255),
    http_status INTEGER,
    action VARCHAR(100),
    status VARCHAR(50),
    response_json JSONB,
    error_message TEXT,
    execution_time_ms FLOAT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_execution_jobs_decision_id ON execution_jobs(decision_id);
CREATE INDEX IF NOT EXISTS ix_execution_jobs_status ON execution_jobs(status);
CREATE INDEX IF NOT EXISTS ix_execution_jobs_action ON execution_jobs(action);
CREATE INDEX IF NOT EXISTS ix_execution_jobs_profile_id ON execution_jobs(profile_id);
CREATE INDEX IF NOT EXISTS ix_execution_jobs_country_code ON execution_jobs(country_code);

CREATE INDEX IF NOT EXISTS ix_execution_results_execution_job_id ON execution_results(execution_job_id);
CREATE INDEX IF NOT EXISTS ix_execution_results_decision_id ON execution_results(decision_id);
CREATE INDEX IF NOT EXISTS ix_execution_results_status ON execution_results(status);
CREATE INDEX IF NOT EXISTS ix_execution_results_action ON execution_results(action);
"""


def _row_to_dict(row):
    data = dict(row._mapping)
    for key, value in list(data.items()):
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    return data


def ensure_schema_migrations_table(db):
    db.execute(text(CREATE_SCHEMA_MIGRATIONS_SQL))
    db.commit()


def get_database_version():
    db = SessionLocal()
    try:
        ensure_schema_migrations_table(db)
        rows = db.execute(
            text(
                """
                SELECT version, name, status, applied_at, details
                FROM schema_migrations
                ORDER BY applied_at DESC, id DESC;
                """
            )
        ).fetchall()
        return {
            "status": "OK",
            "count": len(rows),
            "migrations": [_row_to_dict(row) for row in rows],
        }
    finally:
        db.close()


def get_database_schema():
    db = SessionLocal()
    try:
        tables = db.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name;
                """
            )
        ).fetchall()

        result = []
        for table_row in tables:
            table_name = table_row._mapping["table_name"]
            columns = db.execute(
                text(
                    """
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                    ORDER BY ordinal_position;
                    """
                ),
                {"table_name": table_name},
            ).fetchall()

            indexes = db.execute(
                text(
                    """
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                      AND tablename = :table_name
                    ORDER BY indexname;
                    """
                ),
                {"table_name": table_name},
            ).fetchall()

            result.append({
                "table": table_name,
                "columns": [_row_to_dict(row) for row in columns],
                "indexes": [_row_to_dict(row) for row in indexes],
            })

        return {"status": "OK", "tables": result}
    finally:
        db.close()


def migrate_v3_4_1_execution_framework():
    db = SessionLocal()
    try:
        ensure_schema_migrations_table(db)

        existing = db.execute(
            text("SELECT version FROM schema_migrations WHERE version = 'v3.4.1';")
        ).fetchone()

        if existing:
            return {
                "status": "SKIPPED",
                "message": "Migration v3.4.1 has already been applied.",
                "version": "v3.4.1",
            }

        db.execute(text(MIGRATION_V3_4_1_SQL))
        db.execute(
            text(
                """
                INSERT INTO schema_migrations (version, name, status, applied_at, details)
                VALUES (
                    'v3.4.1',
                    'Execution framework',
                    'APPLIED',
                    NOW(),
                    '{
                      "tables": ["execution_jobs", "execution_results"],
                      "mode": "dry_run_only",
                      "live_execution": false
                    }'::JSONB
                )
                ON CONFLICT (version) DO NOTHING;
                """
            )
        )
        db.commit()

        return {
            "status": "OK",
            "message": "Migration v3.4.1 applied successfully.",
            "version": "v3.4.1",
        }

    except Exception as exc:
        db.rollback()
        return {
            "status": "ERROR",
            "message": "Migration v3.4.1 failed.",
            "error": str(exc),
        }
    finally:
        db.close()
