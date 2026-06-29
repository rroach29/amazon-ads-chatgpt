import os
from datetime import datetime, timezone
from sqlalchemy import text

from database import SessionLocal


CREATE_MARKETPLACE_PROFILES_SQL = """
CREATE TABLE IF NOT EXISTS marketplace_profiles (
    id SERIAL PRIMARY KEY,
    profile_id VARCHAR(100) UNIQUE NOT NULL,
    country_code VARCHAR(10) NOT NULL,
    marketplace VARCHAR(100),
    currency VARCHAR(10),
    account_name VARCHAR(255),
    timezone VARCHAR(100),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
"""


UPSERT_PROFILE_SQL = """
INSERT INTO marketplace_profiles (
    profile_id,
    country_code,
    marketplace,
    currency,
    account_name,
    timezone,
    active,
    created_at,
    updated_at
)
VALUES (
    :profile_id,
    :country_code,
    :marketplace,
    :currency,
    :account_name,
    :timezone,
    :active,
    :created_at,
    :updated_at
)
ON CONFLICT (profile_id)
DO UPDATE SET
    country_code = EXCLUDED.country_code,
    marketplace = EXCLUDED.marketplace,
    currency = EXCLUDED.currency,
    account_name = EXCLUDED.account_name,
    timezone = EXCLUDED.timezone,
    active = EXCLUDED.active,
    updated_at = EXCLUDED.updated_at
RETURNING id;
"""


SELECT_PROFILES_SQL = """
SELECT
    id,
    profile_id,
    country_code,
    marketplace,
    currency,
    account_name,
    timezone,
    active,
    created_at,
    updated_at
FROM marketplace_profiles
ORDER BY country_code ASC, id ASC;
"""


SELECT_ACTIVE_PROFILES_SQL = """
SELECT
    id,
    profile_id,
    country_code,
    marketplace,
    currency,
    account_name,
    timezone,
    active,
    created_at,
    updated_at
FROM marketplace_profiles
WHERE active = TRUE
ORDER BY country_code ASC, id ASC;
"""


SELECT_PROFILE_BY_COUNTRY_SQL = """
SELECT
    id,
    profile_id,
    country_code,
    marketplace,
    currency,
    account_name,
    timezone,
    active,
    created_at,
    updated_at
FROM marketplace_profiles
WHERE UPPER(country_code) = UPPER(:country_code)
LIMIT 1;
"""


def ensure_marketplace_profiles_table(db):
    db.execute(text(CREATE_MARKETPLACE_PROFILES_SQL))
    db.commit()


def _row_to_dict(row):
    data = dict(row._mapping)

    for key in ["created_at", "updated_at"]:
        if data.get(key):
            data[key] = data[key].isoformat()

    return data


def seed_default_us_profile():
    """Create a US profile from the existing single-profile environment variables."""
    profile_id = os.getenv("AMAZON_PROFILE_ID")

    if not profile_id:
        return {
            "status": "SKIPPED",
            "message": "AMAZON_PROFILE_ID is not set.",
        }

    return upsert_marketplace_profile(
        profile_id=profile_id,
        country_code="US",
        marketplace="amazon.com",
        currency="USD",
        account_name="Amazon Ads US",
        timezone="America/Los_Angeles",
        active=True,
    )


def upsert_marketplace_profile(
    profile_id,
    country_code,
    marketplace=None,
    currency=None,
    account_name=None,
    timezone=None,
    active=True,
):
    db = SessionLocal()

    try:
        ensure_marketplace_profiles_table(db)

        now = datetime.now(timezone_utc := timezone_module())

        result = db.execute(
            text(UPSERT_PROFILE_SQL),
            {
                "profile_id": str(profile_id),
                "country_code": str(country_code).upper(),
                "marketplace": marketplace,
                "currency": currency,
                "account_name": account_name,
                "timezone": timezone,
                "active": active,
                "created_at": now,
                "updated_at": now,
            },
        )

        profile_db_id = result.scalar()
        db.commit()

        return {
            "status": "OK",
            "profile_db_id": profile_db_id,
            "profile_id": str(profile_id),
            "country_code": str(country_code).upper(),
            "marketplace": marketplace,
            "currency": currency,
            "account_name": account_name,
            "timezone": timezone,
            "active": active,
        }

    finally:
        db.close()


def timezone_module():
    return timezone.utc


def list_marketplace_profiles(active_only=False):
    db = SessionLocal()

    try:
        ensure_marketplace_profiles_table(db)

        rows = db.execute(
            text(SELECT_ACTIVE_PROFILES_SQL if active_only else SELECT_PROFILES_SQL)
        ).fetchall()

        return {
            "status": "OK",
            "count": len(rows),
            "items": [_row_to_dict(row) for row in rows],
        }

    finally:
        db.close()


def get_marketplace_profile(country_code="US"):
    db = SessionLocal()

    try:
        ensure_marketplace_profiles_table(db)

        row = db.execute(
            text(SELECT_PROFILE_BY_COUNTRY_SQL),
            {"country_code": country_code},
        ).fetchone()

        if not row:
            return {
                "status": "ERROR",
                "message": f"No marketplace profile found for {country_code}.",
            }

        return {
            "status": "OK",
            "profile": _row_to_dict(row),
        }

    finally:
        db.close()


def add_canada_profile(profile_id):
    return upsert_marketplace_profile(
        profile_id=profile_id,
        country_code="CA",
        marketplace="amazon.ca",
        currency="CAD",
        account_name="Amazon Ads Canada",
        timezone="America/Toronto",
        active=True,
    )
