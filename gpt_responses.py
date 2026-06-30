"""
Business OS v3.3.5
GPT Response Optimization

Compact endpoints for ChatGPT Actions to avoid ResponseTooLargeError.
"""

from dashboard import (
    get_latest_dashboard,
    get_top_campaigns,
    get_waste_campaigns,
    get_winning_search_terms,
    get_wasted_search_terms,
)
from marketplace_summary import build_marketplace_summary, compare_marketplaces
from decision_history import get_decision_history
from decision_metrics import get_decision_metrics
from ai.decision_engine import build_decisions
from forecasting.engine import forecast_open_decisions


def _take(items, limit=5):
    return items[:limit] if isinstance(items, list) else []


def _compact_campaign(row):
    return {
        "campaign_name": row.get("campaign_name"),
        "country_code": row.get("country_code"),
        "marketplace": row.get("marketplace"),
        "currency": row.get("currency"),
        "spend": row.get("spend"),
        "sales": row.get("sales"),
        "orders": row.get("orders"),
        "acos": row.get("acos"),
        "roas": row.get("roas"),
    }


def _compact_search_term(row):
    return {
        "search_term": row.get("search_term"),
        "campaign_name": row.get("campaign_name"),
        "country_code": row.get("country_code"),
        "marketplace": row.get("marketplace"),
        "currency": row.get("currency"),
        "spend": row.get("spend"),
        "sales": row.get("sales"),
        "orders": row.get("orders"),
        "acos": row.get("acos"),
        "roas": row.get("roas"),
    }


def _compact_decision(row):
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    return {
        "id": row.get("id"),
        "decision": row.get("decision"),
        "priority": row.get("priority"),
        "confidence": row.get("confidence"),
        "estimated_monthly_impact": row.get("estimated_monthly_impact"),
        "recommended_action": row.get("recommended_action"),
        "campaign_name": payload.get("campaign_name"),
        "search_term": payload.get("search_term"),
        "keyword": payload.get("keyword"),
        "spend": payload.get("spend"),
        "sales": payload.get("sales"),
        "orders": payload.get("orders"),
        "acos": payload.get("acos"),
        "data_window": payload.get("data_window"),
    }


def _compact_marketplace_summary(summary):
    if not isinstance(summary, dict):
        return {}

    combined = summary.get("combined", {})
    marketplaces = []

    for item in summary.get("marketplaces", []):
        marketplaces.append({
            "country_code": item.get("country_code"),
            "marketplace": item.get("marketplace"),
            "currency": item.get("currency"),
            "health_score": item.get("health_score"),
            "spend": item.get("spend"),
            "sales": item.get("sales"),
            "orders": item.get("orders"),
            "acos": item.get("acos"),
            "roas": item.get("roas"),
        })

    return {
        "active_marketplaces": summary.get("active_marketplaces"),
        "marketplaces_with_data": summary.get("marketplaces_with_data"),
        "combined": {
            "spend": combined.get("spend"),
            "sales": combined.get("sales"),
            "orders": combined.get("orders"),
            "acos": combined.get("acos"),
            "roas": combined.get("roas"),
            "average_health_score": combined.get("average_health_score"),
        },
        "marketplaces": marketplaces,
        "best_by_sales": summary.get("best_by_sales"),
        "best_by_roas": summary.get("best_by_roas"),
        "needs_attention": summary.get("needs_attention"),
    }


def get_gpt_dashboard(country_code=None, profile_id=None):
    dashboard = get_latest_dashboard(country_code=country_code, profile_id=profile_id)
    top_campaigns = get_top_campaigns(limit=5, country_code=country_code, profile_id=profile_id)
    waste_campaigns = get_waste_campaigns(min_spend=5, limit=5, country_code=country_code, profile_id=profile_id)
    winning_terms = get_winning_search_terms(max_acos=35, min_orders=1, limit=5, country_code=country_code, profile_id=profile_id)
    wasted_terms = get_wasted_search_terms(min_spend=3, limit=5, country_code=country_code, profile_id=profile_id)

    return {
        "status": "OK",
        "mode": "gpt_compact",
        "dashboard": dashboard,
        "top_campaigns": [_compact_campaign(item) for item in top_campaigns.get("campaigns", [])],
        "waste_campaigns": [_compact_campaign(item) for item in waste_campaigns.get("campaigns", [])],
        "winning_search_terms": [_compact_search_term(item) for item in winning_terms.get("search_terms", [])],
        "wasted_search_terms": [_compact_search_term(item) for item in wasted_terms.get("search_terms", [])],
    }


def get_gpt_morning_brief(country_code=None, profile_id=None, compare_to="US"):
    marketplace_summary = build_marketplace_summary()
    comparison = None

    if country_code and compare_to:
        comparison = compare_marketplaces(primary_country_code=country_code, comparison_country_code=compare_to)

    dashboard = get_latest_dashboard(country_code=country_code, profile_id=profile_id)
    decisions = get_decision_history(status="OPEN", limit=10)
    decision_items = decisions.get("items", [])

    top_campaigns = get_top_campaigns(limit=5, country_code=country_code, profile_id=profile_id)
    waste_campaigns = get_waste_campaigns(min_spend=5, limit=5, country_code=country_code, profile_id=profile_id)
    wasted_terms = get_wasted_search_terms(min_spend=3, limit=5, country_code=country_code, profile_id=profile_id)
    winning_terms = get_winning_search_terms(max_acos=35, min_orders=1, limit=5, country_code=country_code, profile_id=profile_id)

    compact_decisions = [_compact_decision(item) for item in _take(decision_items, 5)]

    return {
        "status": "OK",
        "mode": "gpt_compact",
        "title": "Business OS Morning Brief",
        "marketplace_summary": _compact_marketplace_summary(marketplace_summary),
        "marketplace_comparison": comparison,
        "dashboard": dashboard,
        "executive_summary": {
            "open_decisions": len(decision_items),
            "top_decision": compact_decisions[0] if compact_decisions else None,
            "combined_sales": marketplace_summary.get("combined", {}).get("sales"),
            "combined_spend": marketplace_summary.get("combined", {}).get("spend"),
            "combined_roas": marketplace_summary.get("combined", {}).get("roas"),
            "best_marketplace_by_roas": marketplace_summary.get("best_by_roas"),
            "marketplace_needing_attention": marketplace_summary.get("needs_attention"),
        },
        "top_open_decisions": compact_decisions,
        "top_campaigns": [_compact_campaign(item) for item in top_campaigns.get("campaigns", [])],
        "waste_campaigns": [_compact_campaign(item) for item in waste_campaigns.get("campaigns", [])],
        "wasted_search_terms": [_compact_search_term(item) for item in wasted_terms.get("search_terms", [])],
        "winning_search_terms": [_compact_search_term(item) for item in winning_terms.get("search_terms", [])],
    }


def get_gpt_business_intelligence(country_code=None, profile_id=None, compare_to="US"):
    morning = get_gpt_morning_brief(country_code=country_code, profile_id=profile_id, compare_to=compare_to)
    metrics = get_decision_metrics()
    forecast = forecast_open_decisions()

    return {
        "status": "OK",
        "mode": "gpt_compact",
        "title": "Business Intelligence",
        "executive_summary": morning.get("executive_summary"),
        "marketplace_summary": morning.get("marketplace_summary"),
        "marketplace_comparison": morning.get("marketplace_comparison"),
        "decision_metrics": {
            "status": metrics.get("status"),
            "summary": metrics.get("summary"),
        },
        "business_score": forecast.get("business_score"),
        "recommendation": forecast.get("recommendation"),
        "top_open_decisions": morning.get("top_open_decisions"),
        "top_campaigns": morning.get("top_campaigns"),
        "waste_campaigns": morning.get("waste_campaigns"),
        "wasted_search_terms": morning.get("wasted_search_terms"),
        "winning_search_terms": morning.get("winning_search_terms"),
    }


def get_gpt_root_cause(metric="acos", days=14, country_code=None, compare_to="US"):
    dashboard = get_latest_dashboard(country_code=country_code)
    marketplace_summary = build_marketplace_summary()
    comparison = None

    if country_code and compare_to:
        comparison = compare_marketplaces(primary_country_code=country_code, comparison_country_code=compare_to)

    waste_campaigns = get_waste_campaigns(min_spend=5, limit=5, country_code=country_code)
    wasted_terms = get_wasted_search_terms(min_spend=3, limit=5, country_code=country_code)
    winning_terms = get_winning_search_terms(max_acos=35, min_orders=1, limit=5, country_code=country_code)

    findings = []

    if marketplace_summary.get("needs_attention"):
        findings.append({
            "type": "MARKETPLACE_NEEDS_ATTENTION",
            "reason": "One marketplace has weaker health or efficiency than the others.",
            "item": marketplace_summary.get("needs_attention"),
        })

    if waste_campaigns.get("campaigns"):
        findings.append({
            "type": "WASTED_CAMPAIGN_SPEND",
            "reason": "Campaigns are spending without enough attributed sales.",
            "items": [_compact_campaign(item) for item in waste_campaigns.get("campaigns", [])],
        })

    if wasted_terms.get("search_terms"):
        findings.append({
            "type": "WASTED_SEARCH_TERMS",
            "reason": "Search terms are generating spend without sales.",
            "items": [_compact_search_term(item) for item in wasted_terms.get("search_terms", [])],
        })

    if winning_terms.get("search_terms"):
        findings.append({
            "type": "SEARCH_TERM_WINNERS",
            "reason": "Search terms are converting and may deserve Exact Match targeting.",
            "items": [_compact_search_term(item) for item in winning_terms.get("search_terms", [])],
        })

    return {
        "status": "OK",
        "mode": "gpt_compact",
        "title": "Root Cause Analysis",
        "metric": metric,
        "days": days,
        "dashboard": dashboard,
        "marketplace_summary": _compact_marketplace_summary(marketplace_summary),
        "marketplace_comparison": comparison,
        "findings": findings[:5],
    }


def get_gpt_decisions():
    build_result = build_decisions()
    history = get_decision_history(status="OPEN", limit=10)
    marketplace_summary = build_marketplace_summary()

    return {
        "status": "OK",
        "mode": "gpt_compact",
        "decision_build": {
            "status": build_result.get("status") if isinstance(build_result, dict) else None,
            "count": build_result.get("count") if isinstance(build_result, dict) else None,
            "breakdown": build_result.get("breakdown") if isinstance(build_result, dict) else None,
        },
        "marketplace_summary": _compact_marketplace_summary(marketplace_summary),
        "open_decisions": [_compact_decision(item) for item in history.get("items", [])[:10]],
    }


def get_gpt_forecast():
    forecast = forecast_open_decisions()
    marketplace_summary = build_marketplace_summary()

    return {
        "status": "OK",
        "mode": "gpt_compact",
        "business_score": forecast.get("business_score"),
        "recommendation": forecast.get("recommendation"),
        "marketplace_summary": _compact_marketplace_summary(marketplace_summary),
        "forecast_summary": {
            "status": forecast.get("status"),
            "estimated_monthly_impact": forecast.get("estimated_monthly_impact"),
            "decision_count": forecast.get("decision_count"),
        },
    }
