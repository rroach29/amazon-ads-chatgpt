from business_context import get_business_os_context
from trends import build_trend_summary
from decision_history import get_decision_history

def safe_get(d, *keys, default=None):
    current = d

    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)

    return current if current is not None else default


def money(value):
    return f"${value:,.2f}" if isinstance(value, (int, float)) else "$0.00"


def percent(value):
    return f"{value:.1f}%" if isinstance(value, (int, float)) else "N/A"


def get_list(section, key):
    if not isinstance(section, dict):
        return []
    return section.get(key, []) or []


def build_business_intelligence():
    context = get_business_os_context()
    trends = build_trend_summary(days=14)

    dashboard = context.get("dashboard", {})
    summary = dashboard.get("summary", {})
    open_decisions = get_decision_history(status="OPEN", limit=20)
    decision_items = open_decisions.get("items", [])
    recommendations = get_list(
        context.get("recommendations", {}),
        "recommendations",
    )

    queue_items = get_list(
        context.get("optimization_queue", {}),
        "items",
    )

    top_campaigns = get_list(
        context.get("top_campaigns", {}),
        "campaigns",
    )

    waste_campaigns = get_list(
        context.get("waste_campaigns", {}),
        "campaigns",
    )

    winning_terms = get_list(
        context.get("winning_search_terms", {}),
        "search_terms",
    )

    wasted_terms = get_list(
        context.get("wasted_search_terms", {}),
        "search_terms",
    )

    spend = summary.get("spend") or 0
    sales = summary.get("sales") or 0
    acos = summary.get("acos")
    roas = summary.get("roas")
    orders = summary.get("orders") or 0
    health_score = summary.get("health_score")

    high_priority = [
        r for r in recommendations
        if r.get("priority") == "HIGH"
    ]

    estimated_monthly_savings = round(
        sum(item.get("estimated_monthly_savings") or 0 for item in queue_items),
        2,
    )

    account_score = calculate_account_score(
        health_score,
        acos,
        roas,
        len(high_priority),
        estimated_monthly_savings,
    )

    priorities = build_priorities(
        high_priority,
        waste_campaigns,
        wasted_terms,
        winning_terms,
        top_campaigns,
    )

    opportunities = build_opportunities(
        top_campaigns,
        winning_terms,
        recommendations,
    )

    risks = build_risks(
        waste_campaigns,
        wasted_terms,
        high_priority,
        acos,
    )

    executive_summary = build_executive_summary(
        spend,
        sales,
        acos,
        roas,
        orders,
        account_score,
        high_priority,
        estimated_monthly_savings,
        top_campaigns,
        waste_campaigns,
        wasted_terms,
        winning_terms,
    )

    narrative = build_narrative(
        executive_summary,
        priorities,
        opportunities,
        risks,
        estimated_monthly_savings,
    )

    return {
        "status": "OK",
        "title": "Amazon Ads Business Intelligence",
        "dashboard_date": dashboard.get("date"),
        "account_score": account_score,
        "executive_summary": executive_summary,
        "narrative": narrative,
        "metrics": {
            "spend": spend,
            "sales": sales,
            "acos": acos,
            "roas": roas,
            "orders": orders,
            "health_score": health_score,
        },
        "trend_summary": summarize_trends(trends),
        "decision_intelligence": {
            "open_decision_count": len(decision_items),
            "top_decisions": decision_items[:5],
        },
        "priorities": priorities,
        "opportunities": opportunities,
        "risks": risks,
        "estimated_monthly_savings": estimated_monthly_savings,
    }


def calculate_account_score(
    health_score,
    acos,
    roas,
    high_priority_count,
    estimated_monthly_savings,
):
    score = health_score if isinstance(health_score, int) else 75

    if isinstance(acos, (int, float)):
        if acos <= 25:
            score += 5
        elif acos >= 50:
            score -= 10

    if isinstance(roas, (int, float)):
        if roas >= 4:
            score += 5
        elif roas <= 2:
            score -= 10

    if high_priority_count >= 5:
        score -= 8
    elif high_priority_count == 0:
        score += 3

    if estimated_monthly_savings >= 300:
        score -= 5

    return max(0, min(100, round(score)))


def build_priorities(
    high_priority,
    waste_campaigns,
    wasted_terms,
    winning_terms,
    top_campaigns,
):
    priorities = []

    if high_priority:
        top = high_priority[0]
        priorities.append({
            "rank": 1,
            "priority": "HIGH",
            "title": top.get("title"),
            "reason": top.get("reason"),
            "recommended_action": top.get("type"),
            "confidence": top.get("confidence"),
        })

    if waste_campaigns:
        top = waste_campaigns[0]
        priorities.append({
            "rank": len(priorities) + 1,
            "priority": "HIGH",
            "title": "Review wasted campaign spend",
            "reason": f"{top.get('campaign_name')} is generating spend without enough return.",
            "recommended_action": "REVIEW_OR_PAUSE_CAMPAIGN",
            "campaign_name": top.get("campaign_name"),
            "spend": top.get("spend"),
        })

    if wasted_terms:
        top = wasted_terms[0]
        priorities.append({
            "rank": len(priorities) + 1,
            "priority": "HIGH",
            "title": "Add negative keyword",
            "reason": f"'{top.get('search_term')}' is spending without producing sales.",
            "recommended_action": "ADD_NEGATIVE_KEYWORD",
            "search_term": top.get("search_term"),
            "spend": top.get("spend"),
        })

    if winning_terms:
        top = winning_terms[0]
        priorities.append({
            "rank": len(priorities) + 1,
            "priority": "MEDIUM",
            "title": "Harvest winning search term",
            "reason": f"'{top.get('search_term')}' is converting and may deserve Exact Match targeting.",
            "recommended_action": "HARVEST_KEYWORD",
            "search_term": top.get("search_term"),
            "orders": top.get("orders"),
            "acos": top.get("acos"),
        })

    if top_campaigns:
        top = top_campaigns[0]
        priorities.append({
            "rank": len(priorities) + 1,
            "priority": "MEDIUM",
            "title": "Scale top campaign",
            "reason": f"{top.get('campaign_name')} is one of the strongest current performers.",
            "recommended_action": "SCALE_CAMPAIGN",
            "campaign_name": top.get("campaign_name"),
            "sales": top.get("sales"),
            "acos": top.get("acos"),
        })

    return priorities[:5]


def build_opportunities(top_campaigns, winning_terms, recommendations):
    opportunities = []

    for campaign in top_campaigns[:3]:
        opportunities.append({
            "type": "CAMPAIGN_SCALE",
            "title": f"Scale {campaign.get('campaign_name')}",
            "reason": "This campaign is currently among the top performers.",
            "campaign_name": campaign.get("campaign_name"),
            "sales": campaign.get("sales"),
            "acos": campaign.get("acos"),
        })

    for term in winning_terms[:3]:
        opportunities.append({
            "type": "KEYWORD_HARVEST",
            "title": f"Harvest '{term.get('search_term')}'",
            "reason": "This search term is converting and may deserve Exact Match targeting.",
            "search_term": term.get("search_term"),
            "orders": term.get("orders"),
            "acos": term.get("acos"),
        })

    for rec in recommendations:
        if rec.get("type") in ["SCALE_CAMPAIGN", "HARVEST_KEYWORD"]:
            opportunities.append({
                "type": rec.get("type"),
                "title": rec.get("title"),
                "reason": rec.get("reason"),
                "confidence": rec.get("confidence"),
            })

    return opportunities[:8]


def build_risks(waste_campaigns, wasted_terms, high_priority, acos):
    risks = []

    if isinstance(acos, (int, float)) and acos >= 45:
        risks.append({
            "severity": "HIGH",
            "type": "HIGH_ACOS",
            "title": "ACOS is elevated",
            "reason": f"Current ACOS is {percent(acos)}, which may indicate inefficient spend.",
        })

    if waste_campaigns:
        risks.append({
            "severity": "HIGH",
            "type": "CAMPAIGN_WASTE",
            "title": "Campaign waste detected",
            "reason": f"{len(waste_campaigns)} campaigns are showing wasted spend.",
        })

    if wasted_terms:
        risks.append({
            "severity": "HIGH",
            "type": "SEARCH_TERM_WASTE",
            "title": "Search term waste detected",
            "reason": f"{len(wasted_terms)} search terms are spending without enough return.",
        })

    if len(high_priority) >= 5:
        risks.append({
            "severity": "MEDIUM",
            "type": "OPTIMIZATION_BACKLOG",
            "title": "Optimization backlog is growing",
            "reason": f"There are {len(high_priority)} high-priority recommendations.",
        })

    return risks


def build_executive_summary(
    spend,
    sales,
    acos,
    roas,
    orders,
    account_score,
    high_priority,
    estimated_monthly_savings,
    top_campaigns,
    waste_campaigns,
    wasted_terms,
    winning_terms,
):
    top_campaign = top_campaigns[0].get("campaign_name") if top_campaigns else None
    top_waste = waste_campaigns[0].get("campaign_name") if waste_campaigns else None
    top_term = winning_terms[0].get("search_term") if winning_terms else None

    if account_score >= 85:
        health = "strong"
    elif account_score >= 70:
        health = "stable"
    elif account_score >= 55:
        health = "needs attention"
    else:
        health = "under pressure"

    return {
        "health": health,
        "summary": (
            f"The account is currently {health} with an account score of {account_score}/100. "
            f"Spend is {money(spend)}, sales are {money(sales)}, "
            f"ACOS is {percent(acos)}, and ROAS is {roas or 'N/A'}."
        ),
        "top_win": top_campaign,
        "biggest_problem": top_waste,
        "top_search_term_opportunity": top_term,
        "high_priority_count": len(high_priority),
        "estimated_monthly_savings": estimated_monthly_savings,
        "orders": orders,
    }


def summarize_trends(trends):
    account = trends.get("account_trends", {})
    metrics = account.get("metrics", {})

    return {
        "status": account.get("status"),
        "spend_direction": safe_get(metrics, "spend", "direction"),
        "sales_direction": safe_get(metrics, "sales", "direction"),
        "acos_direction": safe_get(metrics, "acos", "direction"),
        "roas_direction": safe_get(metrics, "roas", "direction"),
        "orders_direction": safe_get(metrics, "orders", "direction"),
    }


def build_narrative(
    executive_summary,
    priorities,
    opportunities,
    risks,
    estimated_monthly_savings,
):
    lines = []

    lines.append(executive_summary.get("summary", ""))

    if executive_summary.get("top_win"):
        lines.append(
            f"The strongest current campaign appears to be {executive_summary['top_win']}."
        )

    if executive_summary.get("biggest_problem"):
        lines.append(
            f"The biggest area needing attention is {executive_summary['biggest_problem']}."
        )

    if executive_summary.get("top_search_term_opportunity"):
        lines.append(
            f"The best keyword opportunity is '{executive_summary['top_search_term_opportunity']}'."
        )

    if priorities:
        top = priorities[0]
        lines.append(
            f"Today's highest-priority task is: {top.get('title')}. {top.get('reason')}"
        )

    if risks:
        lines.append(
            f"There are {len(risks)} active risks to monitor."
        )

    if opportunities:
        lines.append(
            f"There are {len(opportunities)} growth opportunities available."
        )

    if estimated_monthly_savings:
        lines.append(
            f"Estimated monthly savings from pending optimizations is {money(estimated_monthly_savings)}."
        )

    return " ".join(lines)
