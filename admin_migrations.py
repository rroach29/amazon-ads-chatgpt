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


MIGRATION_V3_3_3_SQL = """
ALTER TABLE scheduled_report_jobs
    ADD COLUMN IF NOT EXISTS profile_id VARCHAR(100),
    ADD COLUMN IF NOT EXISTS country_code VARCHAR(10),
    ADD COLUMN IF NOT EXISTS marketplace VARCHAR(100),
    ADD COLUMN IF NOT EXISTS currency VARCHAR(10);

ALTER TABLE campaign_daily_details
    ADD COLUMN IF NOT EXISTS profile_id VARCHAR(100),
    ADD COLUMN IF NOT EXISTS country_code VARCHAR(10),
    ADD COLUMN IF NOT EXISTS marketplace VARCHAR(100),
    ADD COLUMN IF NOT EXISTS currency VARCHAR(10);

ALTER TABLE search_term_daily_details
    ADD COLUMN IF NOT EXISTS profile_id VARCHAR(100),
    ADD COLUMN IF NOT EXISTS country_code VARCHAR(10),
    ADD COLUMN IF NOT EXISTS marketplace VARCHAR(100),
    ADD COLUMN IF NOT EXISTS currency VARCHAR(10);

ALTER TABLE daily_dashboards
    ADD COLUMN IF NOT EXISTS profile_id VARCHAR(100),
    ADD COLUMN IF NOT EXISTS country_code VARCHAR(10),
    ADD COLUMN IF NOT EXISTS marketplace VARCHAR(100),
    ADD COLUMN IF NOT EXISTS currency VARCHAR(10);

ALTER TABLE daily_dashboards
    DROP CONSTRAINT IF EXISTS daily_dashboards_date_key;

DROP INDEX IF EXISTS ix_daily_dashboards_date;

CREATE INDEX IF NOT EXISTS ix_scheduled_report_jobs_profile_id ON scheduled_report_jobs(profile_id);
CREATE INDEX IF NOT EXISTS ix_scheduled_report_jobs_country_code ON scheduled_report_jobs(country_code);

CREATE INDEX IF NOT EXISTS ix_campaign_daily_details_profile_id ON campaign_daily_details(profile_id);
CREATE INDEX IF NOT EXISTS ix_campaign_daily_details_country_code ON campaign_daily_details(country_code);

CREATE INDEX IF NOT EXISTS ix_search_term_daily_details_profile_id ON search_term_daily_details(profile_id);
CREATE INDEX IF NOT EXISTS ix_search_term_daily_details_country_code ON search_term_daily_details(country_code);

CREATE INDEX IF NOT EXISTS ix_daily_dashboards_profile_id ON daily_dashboards(profile_id);
CREATE INDEX IF NOT EXISTS ix_daily_dashboards_country_code ON daily_dashboards(country_code);

CREATE UNIQUE INDEX IF NOT EXISTS ux_daily_dashboards_date_profile
ON daily_dashboards(date, profile_id)
WHERE profile_id IS NOT NULL;
"""


ROLLBACK_V3_3_3_SQL = """
DROP INDEX IF EXISTS ux_daily_dashboards_date_profile;

DROP INDEX IF EXISTS ix_scheduled_report_jobs_profile_id;
DROP INDEX IF EXISTS ix_scheduled_report_jobs_country_code;
DROP INDEX IF EXISTS ix_campaign_daily_details_profile_id;
DROP INDEX IF EXISTS ix_campaign_daily_details_country_code;
DROP INDEX IF EXISTS ix_search_term_daily_details_profile_id;
DROP INDEX IF EXISTS ix_search_term_daily_details_country_code;
DROP INDEX IF EXISTS ix_daily_dashboards_profile_id;
DROP INDEX IF EXISTS ix_daily_dashboards_country_code;

ALTER TABLE scheduled_report_jobs
    DROP COLUMN IF EXISTS profile_id,
    DROP COLUMN IF EXISTS country_code,
    DROP COLUMN IF EXISTS marketplace,
    DROP COLUMN IF EXISTS currency;

ALTER TABLE campaign_daily_details
    DROP COLUMN IF EXISTS profile_id,
    DROP COLUMN IF EXISTS country_code,
    DROP COLUMN IF EXISTS marketplace,
    DROP COLUMN IF EXISTS currency;

ALTER TABLE search_term_daily_details
    DROP COLUMN IF EXISTS profile_id,
    DROP COLUMN IF EXISTS country_code,
    DROP COLUMN IF EXISTS marketplace,
    DROP COLUMN IF EXISTS currency;

ALTER TABLE daily_dashboards
    DROP COLUMN IF EXISTS profile_id,
    DROP COLUMN IF EXISTS country_code,
    DROP COLUMN IF EXISTS marketplace,
    DROP COLUMN IF EXISTS currency;

DELETE FROM schema_migrations WHERE version = 'v3.3.3';
"""


REPAIR_DAILY_DASHBOARD_INDEX_SQL = """
ALTER TABLE daily_dashboards
    DROP CONSTRAINT IF EXISTS daily_dashboards_date_key;

DROP INDEX IF EXISTS ix_daily_dashboards_date;

CREATE UNIQUE INDEX IF NOT EXISTS ux_daily_dashboards_date_profile
ON daily_dashboards(date, profile_id)
WHERE profile_id IS NOT NULL;
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
                    SELECT
                        column_name,
                        data_type,
                        is_nullable,
                        column_default
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

            result.append(
                {
                    "table": table_name,
                    "columns": [_row_to_dict(row) for row in columns],
                    "indexes": [_row_to_dict(row) for row in indexes],
                }
            )

        return {
            "status": "OK",
            "tables": result,
        }
    finally:
        db.close()


def get_daily_dashboard_indexes():
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = 'daily_dashboards'
                ORDER BY indexname;
                """
            )
        ).fetchall()

        return {
            "status": "OK",
            "table": "daily_dashboards",
            "indexes": [_row_to_dict(row) for row in rows],
        }

    finally:
        db.close()


def migrate_v3_3_3_marketplace_storage():
    db = SessionLocal()
    try:
        ensure_schema_migrations_table(db)

        existing = db.execute(
            text("SELECT version FROM schema_migrations WHERE version = 'v3.3.3';")
        ).fetchone()

        if existing:
            return {
                "status": "SKIPPED",
                "message": "Migration v3.3.3 has already been applied.",
                "version": "v3.3.3",
            }

        db.execute(text(MIGRATION_V3_3_3_SQL))

        db.execute(
            text(
                """
                INSERT INTO schema_migrations (version, name, status, applied_at, details)
                VALUES (
                    'v3.3.3',
                    'Marketplace-aware storage',
                    'APPLIED',
                    NOW(),
                    CAST(:details AS JSONB)
                );
                """
            ),
            {
                "details": """
                {
                  "tables": [
                    "scheduled_report_jobs",
                    "campaign_daily_details",
                    "search_term_daily_details",
                    "daily_dashboards"
                  ],
                  "fields_added": [
                    "profile_id",
                    "country_code",
                    "marketplace",
                    "currency"
                  ]
                }
                """
            },
        )

        db.commit()

        return {
            "status": "OK",
            "message": "Migration v3.3.3 applied successfully.",
            "version": "v3.3.3",
        }

    except Exception as exc:
        db.rollback()
        return {
            "status": "ERROR",
            "message": "Migration v3.3.3 failed.",
            "error": str(exc),
        }
    finally:
        db.close()


def repair_daily_dashboard_marketplace_index():
    """
    Business OS v3.3.3b

    Repairs old date-only uniqueness on daily_dashboards.

    Required because older SQLAlchemy created a unique index named:
        ix_daily_dashboards_date

    Multi-market storage requires:
        ux_daily_dashboards_date_profile on (date, profile_id)
    """
    db = SessionLocal()

    try:
        before = db.execute(
            text(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = 'daily_dashboards'
                ORDER BY indexname;
                """
            )
        ).fetchall()

        db.execute(text(REPAIR_DAILY_DASHBOARD_INDEX_SQL))
        db.commit()

        after = db.execute(
            text(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = 'daily_dashboards'
                ORDER BY indexname;
                """
            )
        ).fetchall()

        return {
            "status": "OK",
            "message": "daily_dashboards marketplace-aware index repaired.",
            "before": [_row_to_dict(row) for row in before],
            "after": [_row_to_dict(row) for row in after],
        }

    except Exception as exc:
        db.rollback()
        return {
            "status": "ERROR",
            "message": "daily_dashboards index repair failed.",
            "error": str(exc),
        }

    finally:
        db.close()


def rollback_v3_3_3_marketplace_storage(confirm: bool = False):
    if not confirm:
        return {
            "status": "CONFIRMATION_REQUIRED",
            "message": "Rollback is destructive. Re-run with confirm=true to continue.",
        }

    db = SessionLocal()
    try:
        ensure_schema_migrations_table(db)
        db.execute(text(ROLLBACK_V3_3_3_SQL))
        db.commit()

        return {
            "status": "OK",
            "message": "Migration v3.3.3 rollback completed.",
            "version": "v3.3.3",
        }

    except Exception as exc:
        db.rollback()
        return {
            "status": "ERROR",
            "message": "Rollback v3.3.3 failed.",
            "error": str(exc),
        }
    finally:
        db.close()
