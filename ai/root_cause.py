from business_context import get_business_os_context
from marketplace_summary import build_marketplace_summary, compare_marketplaces


def build_root_cause_analysis(metric="acos", days=14, country_code=None, compare_to="US"):
    context = get_business_os_context()

    dashboard = context.get("dashboard", {})
    summary = dashboard.get("summary", {})

    waste_campaigns = context.get("waste_campaigns", {}).get("campaigns", []) or []
    wasted_search_terms = context.get("wasted_search_terms", {}).get("search_terms", []) or []
    winning_search_terms = context.get("winning_search_terms", {}).get("search_terms", []) or []
    top_campaigns = context.get("top_campaigns", {}).get("campaigns", []) or []

    marketplace_summary = build_marketplace_summary()
    marketplace_comparison = None

    if country_code and compare_to:
        marketplace_comparison = compare_marketplaces(
            primary_country_code=country_code,
            comparison_country_code=compare_to,
        )

    findings = []

    needs_attention = marketplace_summary.get("needs_attention")
    if needs_attention:
        findings.append({
            "type": "MARKETPLACE_NEEDS_ATTENTION",
            "reason": "One marketplace has a weaker current health score or efficiency profile than the others.",
            "items": [needs_attention],
        })

    best_by_roas = marketplace_summary.get("best_by_roas")
    if best_by_roas:
        findings.append({
            "type": "BEST_MARKETPLACE_BY_ROAS",
            "reason": "This marketplace currently has the strongest return on ad spend.",
            "items": [best_by_roas],
        })

    if waste_campaigns:
        findings.append({
            "type": "WASTED_CAMPAIGN_SPEND",
            "reason": "One or more campaigns are spending without enough attributed sales.",
            "items": waste_campaigns[:5],
        })

    if wasted_search_terms:
        findings.append({
            "type": "WASTED_SEARCH_TERMS",
            "reason": "Some search terms are generating clicks and spend without sales.",
            "items": wasted_search_terms[:5],
        })

    if winning_search_terms:
        findings.append({
            "type": "SEARCH_TERM_WINNERS",
            "reason": "Some search terms are converting and may deserve more control or Exact Match targeting.",
            "items": winning_search_terms[:5],
        })

    if top_campaigns:
        findings.append({
            "type": "TOP_CAMPAIGNS",
            "reason": "Top campaigns are driving the strongest current account performance.",
            "items": top_campaigns[:5],
        })

    return {
        "status": "OK",
        "title": "Root Cause Analysis",
        "metric": metric,
        "days": days,
        "country_code": country_code,
        "compare_to": compare_to,
        "account_summary": summary,
        "marketplace_summary": marketplace_summary,
        "marketplace_comparison": marketplace_comparison,
        "findings": findings,
    }
