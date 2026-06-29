from database import SessionLocal
from models import DailyDashboard, CampaignDailyDetail, SearchTermDailyDetail
from marketplace_profiles import list_marketplace_profiles


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return default


def _safe_int(value, default=0):
    try:
        return int(value or default)
    except Exception:
        return default


def _normalize_country_code(country_code):
    return str(country_code).upper() if country_code else None


def _serialize_dashboard(row):
    return {
        "date": str(row.date) if row.date else None,
        "profile_id": row.profile_id,
        "country_code": row.country_code,
        "marketplace": row.marketplace,
        "currency": row.currency,
        "spend": row.spend,
        "sales": row.sales,
        "acos": row.acos,
        "roas": row.roas,
        "clicks": row.clicks,
        "impressions": row.impressions,
        "orders": row.orders,
        "health_score": row.health_score,
    }


def _marketplace_label(row_or_dict):
    country_code = getattr(row_or_dict, "country_code", None)
    marketplace = getattr(row_or_dict, "marketplace", None)

    if isinstance(row_or_dict, dict):
        country_code = row_or_dict.get("country_code")
        marketplace = row_or_dict.get("marketplace")

    if country_code and marketplace:
        return f"{country_code} / {marketplace}"

    return country_code or marketplace or "Unknown marketplace"


def get_latest_marketplace_dashboards():
    """
    Return the latest dashboard row per marketplace profile.

    This is the foundation for marketplace-aware Morning Brief,
    Business Intelligence, Root Cause, and Forecasting.
    """
    db = SessionLocal()

    try:
        rows = (
            db.query(DailyDashboard)
            .filter(DailyDashboard.channel == "amazon_ads")
            .filter(DailyDashboard.profile_id.isnot(None))
            .order_by(DailyDashboard.date.desc(), DailyDashboard.created_at.desc())
            .all()
        )

        latest_by_profile = {}

        for row in rows:
            key = row.profile_id or row.country_code or "unknown"
            if key not in latest_by_profile:
                latest_by_profile[key] = row

        return list(latest_by_profile.values())

    finally:
        db.close()


def build_marketplace_summary():
    """
    Build a combined and per-marketplace executive summary.

    This intentionally uses DailyDashboard first because it is already the
    cleanest daily business summary for each marketplace.
    """
    dashboards = get_latest_marketplace_dashboards()

    profiles_response = list_marketplace_profiles(active_only=True)
    active_profiles = profiles_response.get("items", []) if isinstance(profiles_response, dict) else []

    marketplaces = []

    for row in dashboards:
        marketplaces.append(
            {
                "label": _marketplace_label(row),
                "date": str(row.date) if row.date else None,
                "profile_id": row.profile_id,
                "country_code": row.country_code,
                "marketplace": row.marketplace,
                "currency": row.currency,
                "spend": _safe_float(row.spend),
                "sales": _safe_float(row.sales),
                "acos": row.acos,
                "roas": row.roas,
                "clicks": _safe_int(row.clicks),
                "impressions": _safe_int(row.impressions),
                "orders": _safe_int(row.orders),
                "health_score": row.health_score,
            }
        )

    total_spend = round(sum(m["spend"] for m in marketplaces), 2)
    total_sales = round(sum(m["sales"] for m in marketplaces), 2)
    total_clicks = sum(m["clicks"] for m in marketplaces)
    total_impressions = sum(m["impressions"] for m in marketplaces)
    total_orders = sum(m["orders"] for m in marketplaces)

    combined_acos = round(total_spend / total_sales * 100, 2) if total_sales > 0 else None
    combined_roas = round(total_sales / total_spend, 2) if total_spend > 0 else None

    marketplaces_by_sales = sorted(
        marketplaces,
        key=lambda item: item.get("sales") or 0,
        reverse=True,
    )

    marketplaces_by_roas = sorted(
        [item for item in marketplaces if item.get("roas") is not None],
        key=lambda item: item.get("roas") or 0,
        reverse=True,
    )

    marketplaces_needing_attention = sorted(
        marketplaces,
        key=lambda item: (
            item.get("health_score") if item.get("health_score") is not None else 999,
            -1 * (item.get("spend") or 0),
        ),
    )

    active_country_codes = {
        _normalize_country_code(profile.get("country_code"))
        for profile in active_profiles
        if profile.get("country_code")
    }

    data_country_codes = {
        _normalize_country_code(marketplace.get("country_code"))
        for marketplace in marketplaces
        if marketplace.get("country_code")
    }

    missing_data_marketplaces = [
        profile
        for profile in active_profiles
        if _normalize_country_code(profile.get("country_code")) not in data_country_codes
    ]

    average_health_score = None
    health_scores = [
        item.get("health_score")
        for item in marketplaces
        if item.get("health_score") is not None
    ]

    if health_scores:
        average_health_score = round(sum(health_scores) / len(health_scores))

    return {
        "status": "OK",
        "active_marketplaces": len(active_profiles),
        "marketplaces_with_data": len(marketplaces),
        "missing_data_marketplaces": missing_data_marketplaces,
        "combined": {
            "spend": total_spend,
            "sales": total_sales,
            "acos": combined_acos,
            "roas": combined_roas,
            "clicks": total_clicks,
            "impressions": total_impressions,
            "orders": total_orders,
            "average_health_score": average_health_score,
        },
        "marketplaces": marketplaces,
        "best_by_sales": marketplaces_by_sales[0] if marketplaces_by_sales else None,
        "best_by_roas": marketplaces_by_roas[0] if marketplaces_by_roas else None,
        "needs_attention": marketplaces_needing_attention[0] if marketplaces_needing_attention else None,
    }


def get_marketplace_dashboard(country_code=None, profile_id=None):
    country_code = _normalize_country_code(country_code)

    db = SessionLocal()

    try:
        query = (
            db.query(DailyDashboard)
            .filter(DailyDashboard.channel == "amazon_ads")
        )

        if profile_id:
            query = query.filter(DailyDashboard.profile_id == str(profile_id))
        elif country_code:
            query = query.filter(DailyDashboard.country_code == country_code)

        row = query.order_by(DailyDashboard.date.desc(), DailyDashboard.created_at.desc()).first()

        if not row:
            return {
                "status": "NO_DATA",
                "country_code": country_code,
                "profile_id": str(profile_id) if profile_id else None,
                "message": "No marketplace dashboard data found.",
            }

        return {
            "status": "OK",
            "dashboard": _serialize_dashboard(row),
        }

    finally:
        db.close()


def compare_marketplaces(primary_country_code="CA", comparison_country_code="US"):
    primary = get_marketplace_dashboard(country_code=primary_country_code)
    comparison = get_marketplace_dashboard(country_code=comparison_country_code)

    if primary.get("status") != "OK" or comparison.get("status") != "OK":
        return {
            "status": "NO_DATA",
            "primary": primary,
            "comparison": comparison,
            "message": "One or both marketplaces do not have dashboard data yet.",
        }

    a = primary["dashboard"]
    b = comparison["dashboard"]

    def diff(metric):
        av = _safe_float(a.get(metric))
        bv = _safe_float(b.get(metric))
        return {
            "primary": av,
            "comparison": bv,
            "difference": round(av - bv, 2),
            "percent_difference": round((av - bv) / bv * 100, 2) if bv else None,
        }

    return {
        "status": "OK",
        "primary_country_code": _normalize_country_code(primary_country_code),
        "comparison_country_code": _normalize_country_code(comparison_country_code),
        "primary": a,
        "comparison": b,
        "metrics": {
            "spend": diff("spend"),
            "sales": diff("sales"),
            "orders": diff("orders"),
            "roas": diff("roas"),
            "acos": diff("acos"),
            "health_score": diff("health_score"),
        },
    }
