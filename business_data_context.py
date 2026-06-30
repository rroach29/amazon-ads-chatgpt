"""
Business OS v5.0.2
Data Context Source-of-Truth Fix

Fix:
- resolve_data_context(window="latest") now uses dashboard.get_latest_dashboard()
  instead of duplicating SQL against DailyDashboard.
- This ensures the Data Context and Dashboard endpoints agree on the latest
  reporting date.

Why:
The dashboard endpoint could return a valid latest dashboard date while
business_data_context returned NO_DATA. That meant Business Plans and Mission
Control had a null planning window.
"""

from datetime import date, timedelta


VALID_WINDOWS = {
    "latest",
    "yesterday",
    "last_7_days",
    "last_14_days",
    "last_30_days",
}


def _serialize_date(value):
    if not value:
        return None

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value)


def _parse_date(value):
    if not value:
        return None

    if isinstance(value, date):
        return value

    return date.fromisoformat(str(value))


def get_latest_dashboard_date(country_code=None, profile_id=None):
    """
    Single source of truth for latest reporting date.

    Do not query DailyDashboard directly here. dashboard.get_latest_dashboard()
    already contains the app's working marketplace/latest-date lookup logic.
    """
    try:
        from dashboard import get_latest_dashboard

        dashboard = get_latest_dashboard(
            country_code=country_code,
            profile_id=profile_id,
        )

        if isinstance(dashboard, dict) and dashboard.get("status") == "OK":
            return _parse_date(dashboard.get("date"))

    except Exception:
        # Fallback only for import-cycle or unexpected runtime issues.
        pass

    # Conservative fallback: direct DB query with normalized country code.
    try:
        from database import SessionLocal
        from models import DailyDashboard

        db = SessionLocal()

        try:
            query = db.query(DailyDashboard.date)

            # Some older rows may not have channel consistently populated.
            if hasattr(DailyDashboard, "channel"):
                query = query.filter(
                    (DailyDashboard.channel == "amazon_ads") |
                    (DailyDashboard.channel.is_(None))
                )

            if country_code and hasattr(DailyDashboard, "country_code"):
                query = query.filter(DailyDashboard.country_code == str(country_code).upper())

            if profile_id and hasattr(DailyDashboard, "profile_id"):
                query = query.filter(DailyDashboard.profile_id == str(profile_id))

            latest = query.order_by(DailyDashboard.date.desc()).first()

            return latest[0] if latest else None

        finally:
            db.close()

    except Exception:
        return None


def resolve_data_context(
    window="latest",
    country_code=None,
    profile_id=None,
    start_date=None,
    end_date=None,
):
    """
    Returns a normalized data context for all analytics modules.

    window:
    - latest: latest dashboard date from dashboard.get_latest_dashboard()
    - yesterday: calendar yesterday
    - last_7_days / last_14_days / last_30_days: ending on latest dashboard date
    - custom: explicit start_date/end_date
    """

    normalized_country_code = str(country_code).upper() if country_code else None

    if start_date and end_date:
        resolved_start = _parse_date(start_date)
        resolved_end = _parse_date(end_date)
        resolved_window = "custom"
    else:
        resolved_window = window or "latest"

        if resolved_window not in VALID_WINDOWS:
            resolved_window = "latest"

        if resolved_window == "latest":
            latest = get_latest_dashboard_date(
                country_code=normalized_country_code,
                profile_id=profile_id,
            )
            resolved_start = latest
            resolved_end = latest

        elif resolved_window == "yesterday":
            resolved_end = date.today() - timedelta(days=1)
            resolved_start = resolved_end

        else:
            days = {
                "last_7_days": 7,
                "last_14_days": 14,
                "last_30_days": 30,
            }[resolved_window]

            latest = get_latest_dashboard_date(
                country_code=normalized_country_code,
                profile_id=profile_id,
            )
            resolved_end = latest or (date.today() - timedelta(days=1))
            resolved_start = resolved_end - timedelta(days=days - 1)

    return {
        "status": "OK" if resolved_start and resolved_end else "NO_DATA",
        "window": resolved_window,
        "start_date": _serialize_date(resolved_start),
        "end_date": _serialize_date(resolved_end),
        "country_code": normalized_country_code,
        "profile_id": str(profile_id) if profile_id else None,
        "channel": "amazon_ads",
        "source_of_truth": "dashboard.get_latest_dashboard",
    }


def apply_date_context(query, model, context):
    """
    Adds date filters to SQLAlchemy queries for models with a date column.
    """
    if not context:
        return query

    start_date = context.get("start_date")
    end_date = context.get("end_date")

    if start_date:
        query = query.filter(model.date >= start_date)

    if end_date:
        query = query.filter(model.date <= end_date)

    return query


def apply_marketplace_context(query, model, context):
    """
    Adds marketplace filters to SQLAlchemy queries when the model supports them.
    """
    if not context:
        return query

    country_code = context.get("country_code")
    profile_id = context.get("profile_id")

    if country_code and hasattr(model, "country_code"):
        query = query.filter(model.country_code == str(country_code).upper())

    if profile_id and hasattr(model, "profile_id"):
        query = query.filter(model.profile_id == str(profile_id))

    return query


def explain_data_context(context):
    if not isinstance(context, dict):
        return {
            "status": "ERROR",
            "message": "Invalid data context.",
        }

    return {
        "status": context.get("status"),
        "window": context.get("window"),
        "date_range": {
            "start_date": context.get("start_date"),
            "end_date": context.get("end_date"),
        },
        "marketplace_filter": {
            "country_code": context.get("country_code"),
            "profile_id": context.get("profile_id"),
        },
        "source_of_truth": context.get("source_of_truth"),
        "meaning": (
            "All Business OS intelligence should use this same reporting window "
            "unless an endpoint explicitly requests a different one."
        ),
    }
