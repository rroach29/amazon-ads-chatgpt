from business_context import get_business_os_context
from trends import build_trend_summary
from decision_history import get_decision_history

def get_metric(summary, key, default=0):
    try:
        return summary.get("summary", {}).get(key, default)
    except Exception:
        return default


def get_items(section, key):
    if not isinstance(section, dict):
        return []
    return section.get(key, []) or []


def build_morning_brief():
    context = get_business_os_context()
    trends = build_trend_summary(days=14)
    open_decisions = get_decision_history(status="OPEN", limit=20)
    decision_items = open_decisions.get("items", [])
    dashboard = context.get("dashboard", {})
    dashboard_summary = dashboard.get("summary", {})

    recommendations = get_items(
        context.get("recommendations", {}),
        "recommendations",
    )

    queue_items = get_items(
        context.get("optimization_queue", {}),
        "items",
    )

    top_campaigns = get_items(
        context.get("top_campaigns", {}),
        "campaigns",
    )

    waste_campaigns = get_items(
        context.get("waste_campaigns", {}),
        "campaigns",
    )

    wasted_search_terms = get_items(
        context.get("wasted_search_terms", {}),
        "search_terms",
    )

    winning_search_terms = get_items(
        context.get("winning_search_terms", {}),
        "search_terms",
    )

    high_priority = [
        r for r in recommendations
        if r.get("priority") == "HIGH"
    ]

    estimated_monthly_savings = sum(
        item.get("estimated_monthly_savings") or 0
        for item in queue_items
    )

    account_trends = trends.get("account_trends", {})
    trend_metrics = account_trends.get("metrics", {})

    return {
        "status": "OK",
        "title": "Amazon Ads Morning Brief",
        "dashboard_date": dashboard.get("date"),
        "decisions": {
            "open_count": len(decision_items),
            "top_open_decisions": decision_items[:5],
        },
        "account_health": {
            "health_score": dashboard_summary.get("health_score"),
            "spend": dashboard_summary.get("spend"),
            "sales": dashboard_summary.get("sales"),
            "acos": dashboard_summary.get("acos"),
            "roas": dashboard_summary.get("roas"),
            "clicks": dashboard_summary.get("clicks"),
            "orders": dashboard_summary.get("orders"),
            "impressions": dashboard_summary.get("impressions"),
        },
        "trend_snapshot": {
            "status": account_trends.get("status"),
            "days": trends.get("days"),
            "spend": trend_metrics.get("spend"),
            "sales": trend_metrics.get("sales"),
            "acos": trend_metrics.get("acos"),
            "roas": trend_metrics.get("roas"),
            "orders": trend_metrics.get("orders"),
        },
        "priorities": {
            "high_priority_count": len(high_priority),
            "pending_queue_count": len(queue_items),
            "estimated_monthly_savings": round(estimated_monthly_savings, 2),
            "top_recommendations": recommendations[:5],
        },
        "winners": {
            "top_campaigns": top_campaigns[:5],
            "winning_search_terms": winning_search_terms[:5],
        },
        "needs_attention": {
            "waste_campaigns": waste_campaigns[:5],
            "wasted_search_terms": wasted_search_terms[:5],
        },
        "suggested_focus_today": build_focus_list(
            high_priority,
            waste_campaigns,
            wasted_search_terms,
            winning_search_terms,
            top_campaigns,
        ),
    }


def build_focus_list(
    high_priority,
    waste_campaigns,
    wasted_search_terms,
    winning_search_terms,
    top_campaigns,
):
    focus = []

    if high_priority:
        focus.append({
            "priority": "HIGH",
            "focus": "Review high-priority optimization recommendations",
            "reason": f"There are {len(high_priority)} high-priority recommendations waiting.",
        })

    if waste_campaigns:
        top = waste_campaigns[0]
        focus.append({
            "priority": "HIGH",
            "focus": "Review wasted campaign spend",
            "reason": f"{top.get('campaign_name')} has wasted spend with little or no return.",
        })

    if wasted_search_terms:
        top = wasted_search_terms[0]
        focus.append({
            "priority": "HIGH",
            "focus": "Add negative keywords",
            "reason": f"'{top.get('search_term')}' is spending without producing sales.",
        })

    if winning_search_terms:
        top = winning_search_terms[0]
        focus.append({
            "priority": "MEDIUM",
            "focus": "Harvest winning search terms",
            "reason": f"'{top.get('search_term')}' is converting and may deserve Exact Match targeting.",
        })

    if top_campaigns:
        top = top_campaigns[0]
        focus.append({
            "priority": "MEDIUM",
            "focus": "Scale best-performing campaigns",
            "reason": f"{top.get('campaign_name')} is one of the current top performers.",
        })

    return focus[:5]
