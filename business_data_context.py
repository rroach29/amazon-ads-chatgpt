"""
Business OS v4.0.0
Unified Data Context

One source of truth for "what reporting window are we analyzing?"

This prevents Morning Brief, Dashboard, Decisions, Winners, Trends, and Forecasts
from silently using different dates or mixed historical windows.
"""

from datetime import date, timedelta

from database import SessionLocal
from models import DailyDashboard


VALID_WINDOWS = {
    "latest",
    "yesterday",
    "last_7_days",
    "last_14_days",
    "last_30_days",
}


def _serialize_date(value):
    return value.isoformat() if value else None


def get_latest_dashboard_date(country_code=None, profile_id=None):
    db = SessionLocal()

    try:
        query = db.query(DailyDashboard.date).filter(DailyDashboard.channel == "amazon_ads")

        if country_code:
            query = query.filter(DailyDashboard.country_code == country_code)

        if profile_id:
            query = query.filter(DailyDashboard.profile_id == profile_id)

        latest = query.order_by(DailyDashboard.date.desc()).first()

        return latest[0] if latest else None

    finally:
        db.close()


def resolve_data_context(
    window="latest",
    country_code=None,
    profile_id=None,
    start_date=None,
    end_date=None,
):
    """
    Returns a normalized context dict for all analytics modules.

    window:
    - latest: latest completed dashboard date
    - yesterday: calendar yesterday
    - last_7_days / last_14_days / last_30_days
    - custom: use explicit start_date/end_date
    """

    if start_date and end_date:
        resolved_start = date.fromisoformat(str(start_date))
        resolved_end = date.fromisoformat(str(end_date))
        resolved_window = "custom"
    else:
        resolved_window = window or "latest"

        if resolved_window not in VALID_WINDOWS:
            resolved_window = "latest"

        if resolved_window == "latest":
            latest = get_latest_dashboard_date(country_code=country_code, profile_id=profile_id)
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

            latest = get_latest_dashboard_date(country_code=country_code, profile_id=profile_id)
            resolved_end = latest or (date.today() - timedelta(days=1))
            resolved_start = resolved_end - timedelta(days=days - 1)

    return {
        "status": "OK" if resolved_start and resolved_end else "NO_DATA",
        "window": resolved_window,
        "start_date": _serialize_date(resolved_start),
        "end_date": _serialize_date(resolved_end),
        "country_code": country_code,
        "profile_id": profile_id,
        "channel": "amazon_ads",
        "source_of_truth": "DailyDashboard.latest_completed_date",
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
        query = query.filter(model.country_code == country_code)

    if profile_id and hasattr(model, "profile_id"):
        query = query.filter(model.profile_id == profile_id)

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
