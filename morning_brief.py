from business_context import get_business_os_context
from trends import build_trend_summary
from decision_history import get_decision_history
from decision_metrics import get_decision_metrics
from ai.decision_engine import build_decisions

def get_metric(summary, key, default=0):
    try:
        return summary.get("summary", {}).get(key, default)
    except Exception:
        return default


def get_items(section, key):
    if not isinstance(section, dict):
        return []
    return section.get(key, []) or []


def get_decision_payload(decision):
    payload = decision.get("payload") or {}
    if isinstance(payload, dict):
        return payload
    return {}


def filter_decisions_by_type(decision_items, decision_type):
    return [
        item for item in decision_items
        if item.get("decision") == decision_type
    ]


def summarize_harvest_decision(decision):
    payload = get_decision_payload(decision)

    keyword = (
        payload.get("keyword")
        or payload.get("search_term")
        or "Unknown keyword"
    )

    target_campaign = (
        payload.get("target_campaign_name")
        or payload.get("target_campaign")
        or "Unknown target campaign"
    )

    return {
        "keyword": keyword,
        "target_campaign": target_campaign,
        "confidence": decision.get("confidence"),
        "priority": decision.get("priority"),
        "estimated_monthly_impact": decision.get("estimated_monthly_impact"),
        "recommended_action": decision.get("recommended_action"),
        "orders": payload.get("orders"),
        "clicks": payload.get("clicks"),
        "sales": payload.get("sales"),
        "spend": payload.get("spend"),
        "acos": payload.get("acos"),
        "source_campaign": (
            payload.get("source_campaign_name")
            or payload.get("source_campaign")
        ),
    }


def summarize_negative_decision(decision):
    payload = get_decision_payload(decision)

    return {
        "search_term": payload.get("search_term"),
        "campaign_name": payload.get("campaign_name"),
        "confidence": decision.get("confidence"),
        "priority": decision.get("priority"),
        "estimated_monthly_impact": decision.get("estimated_monthly_impact"),
        "recommended_action": decision.get("recommended_action"),
        "spend": payload.get("spend"),
        "clicks": payload.get("clicks"),
        "sales": payload.get("sales"),
    }


def summarize_pause_decision(decision):
    payload = get_decision_payload(decision)

    return {
        "campaign_name": payload.get("campaign_name"),
        "confidence": decision.get("confidence"),
        "priority": decision.get("priority"),
        "estimated_monthly_impact": decision.get("estimated_monthly_impact"),
        "recommended_action": decision.get("recommended_action"),
        "spend": payload.get("spend"),
        "clicks": payload.get("clicks"),
        "sales": payload.get("sales"),
    }


def build_morning_brief():
    context = get_business_os_context()
    trends = build_trend_summary(days=14)

    open_decisions = get_decision_history(status="OPEN", limit=50)
    decision_items = open_decisions.get("items", [])
    decision_build_result = build_decisions()
    pause_decisions = filter_decisions_by_type(
        decision_items,
        "PAUSE_CAMPAIGN",
    )

    negative_keyword_decisions = filter_decisions_by_type(
        decision_items,
        "ADD_NEGATIVE_KEYWORD",
    )

    harvest_keyword_decisions = filter_decisions_by_type(
        decision_items,
        "HARVEST_KEYWORD",
    )

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

    decision_estimated_monthly_impact = sum(
        item.get("estimated_monthly_impact") or 0
        for item in decision_items
    )

    account_trends = trends.get("account_trends", {})
    trend_metrics = account_trends.get("metrics", {})
    decision_metrics = get_decision_metrics()

    return {
        "status": "OK",
        "title": "Amazon Ads Morning Brief",
        "dashboard_date": dashboard.get("date"),
        "decision_build": {
            "status": decision_build_result.get("status"),
            "count": decision_build_result.get("count"),
            "history_saved": decision_build_result.get("history_saved"),
            "breakdown": decision_build_result.get("breakdown"),
        },
        "executive_summary": {
            "open_decisions": len(decision_items),
            "pause_campaign_decisions": len(pause_decisions),
            "negative_keyword_decisions": len(negative_keyword_decisions),
            "harvest_keyword_decisions": len(harvest_keyword_decisions),
            "estimated_monthly_decision_impact": round(
                decision_estimated_monthly_impact,
                2,
            ),
            "top_priority": get_top_priority(
                decision_items,
                high_priority,
                waste_campaigns,
                wasted_search_terms,
                harvest_keyword_decisions,
            ),
        },

        "decisions": {
            "open_count": len(decision_items),
            "top_open_decisions": decision_items[:5],
            "by_type": {
                "pause_campaigns": [
                    summarize_pause_decision(d)
                    for d in pause_decisions[:5]
                ],
                "negative_keywords": [
                    summarize_negative_decision(d)
                    for d in negative_keyword_decisions[:5]
                ],
                "harvest_keywords": [
                    summarize_harvest_decision(d)
                    for d in harvest_keyword_decisions[:5]
                ],
            },
        },

        "harvest_opportunities": {
            "count": len(harvest_keyword_decisions),
            "top_keywords": [
                summarize_harvest_decision(d)
                for d in harvest_keyword_decisions[:5]
            ],
        },

        "decision_metrics": decision_metrics,

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
            "estimated_monthly_decision_impact": round(
                decision_estimated_monthly_impact,
                2,
            ),
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
            high_priority=high_priority,
            waste_campaigns=waste_campaigns,
            wasted_search_terms=wasted_search_terms,
            winning_search_terms=winning_search_terms,
            top_campaigns=top_campaigns,
            pause_decisions=pause_decisions,
            negative_keyword_decisions=negative_keyword_decisions,
            harvest_keyword_decisions=harvest_keyword_decisions,
        ),
    }


def get_top_priority(
    decision_items,
    high_priority,
    waste_campaigns,
    wasted_search_terms,
    harvest_keyword_decisions,
):
    if decision_items:
        top = decision_items[0]
        return {
            "source": "decision_engine",
            "decision": top.get("decision"),
            "priority": top.get("priority"),
            "confidence": top.get("confidence"),
            "recommended_action": top.get("recommended_action"),
            "estimated_monthly_impact": top.get("estimated_monthly_impact"),
        }

    if high_priority:
        top = high_priority[0]
        return {
            "source": "recommendation_engine",
            "priority": top.get("priority"),
            "recommended_action": top.get("recommended_action"),
            "estimated_monthly_impact": top.get("estimated_monthly_impact"),
        }

    if waste_campaigns:
        top = waste_campaigns[0]
        return {
            "source": "waste_campaigns",
            "priority": "HIGH",
            "recommended_action": f"Review wasted spend in {top.get('campaign_name')}",
        }

    if wasted_search_terms:
        top = wasted_search_terms[0]
        return {
            "source": "wasted_search_terms",
            "priority": "HIGH",
            "recommended_action": f"Review negative keyword opportunity: {top.get('search_term')}",
        }

    if harvest_keyword_decisions:
        top = harvest_keyword_decisions[0]
        return {
            "source": "harvest_keywords",
            "priority": top.get("priority"),
            "recommended_action": top.get("recommended_action"),
            "estimated_monthly_impact": top.get("estimated_monthly_impact"),
        }

    return {
        "source": "none",
        "priority": "LOW",
        "recommended_action": "No urgent action detected today.",
    }


def build_focus_list(
    high_priority,
    waste_campaigns,
    wasted_search_terms,
    winning_search_terms,
    top_campaigns,
    pause_decisions=None,
    negative_keyword_decisions=None,
    harvest_keyword_decisions=None,
):
    focus = []

    pause_decisions = pause_decisions or []
    negative_keyword_decisions = negative_keyword_decisions or []
    harvest_keyword_decisions = harvest_keyword_decisions or []

    if pause_decisions:
        top = pause_decisions[0]
        payload = get_decision_payload(top)

        focus.append({
            "priority": top.get("priority") or "HIGH",
            "focus": "Review pause campaign decision",
            "reason": (
                f"{payload.get('campaign_name')} meets the pause threshold "
                f"with {payload.get('clicks')} clicks and "
                f"${payload.get('sales')} in sales."
            ),
            "decision": top.get("decision"),
            "confidence": top.get("confidence"),
            "recommended_action": top.get("recommended_action"),
        })

    if negative_keyword_decisions:
        top = negative_keyword_decisions[0]
        payload = get_decision_payload(top)

        focus.append({
            "priority": top.get("priority") or "HIGH",
            "focus": "Review negative keyword decision",
            "reason": (
                f"'{payload.get('search_term')}' is spending without "
                f"producing sales."
            ),
            "decision": top.get("decision"),
            "confidence": top.get("confidence"),
            "recommended_action": top.get("recommended_action"),
        })

    if harvest_keyword_decisions:
        top = harvest_keyword_decisions[0]
        payload = get_decision_payload(top)

        keyword = (
            payload.get("keyword")
            or payload.get("search_term")
            or "this search term"
        )

        target_campaign = (
            payload.get("target_campaign_name")
            or payload.get("target_campaign")
            or "the Exact campaign"
        )

        focus.append({
            "priority": top.get("priority") or "MEDIUM",
            "focus": "Harvest proven search term",
            "reason": (
                f"'{keyword}' has generated {payload.get('orders')} orders "
                f"and should be added as Exact Match to {target_campaign}."
            ),
            "decision": top.get("decision"),
            "confidence": top.get("confidence"),
            "recommended_action": top.get("recommended_action"),
        })

    if high_priority:
        focus.append({
            "priority": "HIGH",
            "focus": "Review high-priority optimization recommendations",
            "reason": (
                f"There are {len(high_priority)} high-priority "
                "recommendations waiting."
            ),
        })

    if waste_campaigns:
        top = waste_campaigns[0]
        focus.append({
            "priority": "HIGH",
            "focus": "Review wasted campaign spend",
            "reason": (
                f"{top.get('campaign_name')} has wasted spend with little "
                "or no return."
            ),
        })

    if wasted_search_terms:
        top = wasted_search_terms[0]
        focus.append({
            "priority": "HIGH",
            "focus": "Add negative keywords",
            "reason": (
                f"'{top.get('search_term')}' is spending without producing sales."
            ),
        })

    if winning_search_terms:
        top = winning_search_terms[0]
        focus.append({
            "priority": "MEDIUM",
            "focus": "Harvest winning search terms",
            "reason": (
                f"'{top.get('search_term')}' is converting and may deserve "
                "Exact Match targeting."
            ),
        })

    if top_campaigns:
        top = top_campaigns[0]
        focus.append({
            "priority": "MEDIUM",
            "focus": "Scale best-performing campaigns",
            "reason": (
                f"{top.get('campaign_name')} is one of the current top performers."
            ),
        })

    return focus[:5]
