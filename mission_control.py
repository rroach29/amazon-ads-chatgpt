"""
Business OS v5.0.1
Mission Control Import Fix

Fixes:
ModuleNotFoundError: No module named 'marketplace_intelligence'

This version avoids that dependency and builds the marketplace summary directly
from dashboard.py / marketplace_profiles.py.
"""

from business_data_context import resolve_data_context
from dashboard import get_latest_dashboard
from marketplace_profiles import list_marketplace_profiles
from business_plan_engine import build_business_plan, get_plan_summary, simulate_business_plan
from decision_history import get_decision_history


def _safe_float(value, default=0):
    try:
        return float(value or default)
    except Exception:
        return default


def _safe_int(value, default=0):
    try:
        return int(value or default)
    except Exception:
        return default


def _dashboard_marketplace_item(country_code, profile_id=None):
    dashboard = get_latest_dashboard(country_code=country_code, profile_id=profile_id)

    if not isinstance(dashboard, dict) or dashboard.get("status") != "OK":
        return None

    summary = dashboard.get("summary") if isinstance(dashboard.get("summary"), dict) else {}

    return {
        "label": f"{dashboard.get('country_code')} / {dashboard.get('marketplace')}",
        "date": dashboard.get("date"),
        "profile_id": dashboard.get("profile_id"),
        "country_code": dashboard.get("country_code"),
        "marketplace": dashboard.get("marketplace"),
        "currency": dashboard.get("currency"),
        "spend": _safe_float(summary.get("spend")),
        "sales": _safe_float(summary.get("sales")),
        "acos": summary.get("acos"),
        "roas": summary.get("roas"),
        "clicks": _safe_int(summary.get("clicks")),
        "impressions": _safe_int(summary.get("impressions")),
        "orders": _safe_int(summary.get("orders")),
        "health_score": summary.get("health_score"),
    }


def get_marketplace_summary_for_mission_control(country_code=None, profile_id=None):
    if country_code or profile_id:
        item = _dashboard_marketplace_item(country_code=country_code, profile_id=profile_id)

        if not item:
            return {
                "status": "NO_DATA",
                "active_marketplaces": 1,
                "marketplaces_with_data": 0,
                "marketplaces": [],
                "combined": {},
            }

        return {
            "status": "OK",
            "active_marketplaces": 1,
            "marketplaces_with_data": 1,
            "marketplaces": [item],
            "combined": {
                "spend": item["spend"],
                "sales": item["sales"],
                "clicks": item["clicks"],
                "impressions": item["impressions"],
                "orders": item["orders"],
                "roas": item["roas"],
                "acos": item["acos"],
                "average_health_score": item["health_score"],
            },
            "best_by_sales": item,
            "best_by_roas": item,
            "needs_attention": item,
        }

    profiles_response = list_marketplace_profiles(active_only=True)
    profiles = profiles_response.get("items", []) if isinstance(profiles_response, dict) else []

    marketplaces = []

    for profile in profiles:
        item = _dashboard_marketplace_item(
            country_code=profile.get("country_code"),
            profile_id=profile.get("profile_id"),
        )

        if item:
            marketplaces.append(item)

    if not marketplaces:
        return {
            "status": "NO_DATA",
            "active_marketplaces": len(profiles),
            "marketplaces_with_data": 0,
            "marketplaces": [],
            "combined": {},
        }

    total_spend = round(sum(_safe_float(row.get("spend")) for row in marketplaces), 2)
    total_sales = round(sum(_safe_float(row.get("sales")) for row in marketplaces), 2)
    total_clicks = sum(_safe_int(row.get("clicks")) for row in marketplaces)
    total_impressions = sum(_safe_int(row.get("impressions")) for row in marketplaces)
    total_orders = sum(_safe_int(row.get("orders")) for row in marketplaces)

    combined_roas = round(total_sales / total_spend, 2) if total_spend else 0
    combined_acos = round((total_spend / total_sales) * 100, 2) if total_sales else None

    health_scores = [
        _safe_float(row.get("health_score"))
        for row in marketplaces
        if row.get("health_score") is not None
    ]

    average_health_score = round(sum(health_scores) / len(health_scores), 2) if health_scores else None

    best_by_sales = max(marketplaces, key=lambda row: _safe_float(row.get("sales")))
    best_by_roas = max(marketplaces, key=lambda row: _safe_float(row.get("roas")))
    needs_attention = min(
        marketplaces,
        key=lambda row: _safe_float(row.get("health_score"), default=999),
    )

    return {
        "status": "OK",
        "active_marketplaces": len(profiles),
        "marketplaces_with_data": len(marketplaces),
        "marketplaces": marketplaces,
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
        "best_by_sales": best_by_sales,
        "best_by_roas": best_by_roas,
        "needs_attention": needs_attention,
    }


def get_mission_control(
    objective=None,
    window="latest",
    country_code=None,
    profile_id=None,
):
    context = resolve_data_context(
        window=window,
        country_code=country_code,
        profile_id=profile_id,
    )

    marketplace_summary = get_marketplace_summary_for_mission_control(
        country_code=country_code,
        profile_id=profile_id,
    )

    plan = build_business_plan(
        objective=objective,
        window=window,
        country_code=country_code,
        profile_id=profile_id,
        max_actions=20,
        min_confidence=70,
        include_high_risk=False,
    )

    simulation = simulate_business_plan(plan)

    decisions = get_decision_history(
        status="OPEN",
        limit=50,
        current_window_only=True,
        include_legacy=False,
    )

    return {
        "status": "OK",
        "title": "Business OS Mission Control",
        "data_context": context,
        "mission": plan.get("mission"),
        "marketplace_summary": marketplace_summary,
        "current_plan": get_plan_summary(plan),
        "simulation": simulation,
        "open_decisions": {
            "count": decisions.get("count"),
            "current_window_only": decisions.get("current_window_only"),
        },
        "operating_mode": {
            "plan_approval_required": True,
            "live_execution_requires_confirm_live": True,
            "high_risk_actions_excluded_by_default": True,
        },
        "recommended_focus": _recommended_focus(plan, marketplace_summary),
    }


def _recommended_focus(plan, marketplace_summary):
    focus = []

    if plan.get("action_count", 0) > 0:
        focus.append({
            "priority": "HIGH",
            "focus": "Review current business plan",
            "reason": f"{plan.get('action_count')} approval-ready actions are available.",
            "expected_monthly_impact": plan.get("expected_monthly_impact"),
        })

    needs_attention = marketplace_summary.get("needs_attention") if isinstance(marketplace_summary, dict) else None

    if needs_attention:
        focus.append({
            "priority": "HIGH",
            "focus": "Review weakest marketplace",
            "reason": f"{needs_attention.get('label')} has the weakest current health score.",
            "marketplace": needs_attention,
        })

    if not focus:
        focus.append({
            "priority": "LOW",
            "focus": "Monitor",
            "reason": "No high-confidence approval-ready actions are available for the current data window.",
        })

    return focus
