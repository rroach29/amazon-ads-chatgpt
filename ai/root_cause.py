from business_context import get_business_os_context


def build_root_cause_analysis():
    context = get_business_os_context()

    dashboard = context.get("dashboard", {})
    summary = dashboard.get("summary", {})

    waste_campaigns = context.get("waste_campaigns", {}).get("campaigns", []) or []
    wasted_search_terms = context.get("wasted_search_terms", {}).get("search_terms", []) or []
    winning_search_terms = context.get("winning_search_terms", {}).get("search_terms", []) or []
    top_campaigns = context.get("top_campaigns", {}).get("campaigns", []) or []

    findings = []

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
        "account_summary": summary,
        "findings": findings,
    }