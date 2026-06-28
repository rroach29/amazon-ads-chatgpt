def money(value):
    try:
        return round(float(value or 0), 2)
    except Exception:
        return 0.0


def integer(value):
    try:
        return int(value or 0)
    except Exception:
        return 0


def enrich_rows(rows):
    enriched = []

    for row in rows:
        spend = money(row.get("cost"))
        sales = money(row.get("sales7d"))
        clicks = integer(row.get("clicks"))
        impressions = integer(row.get("impressions"))
        orders = integer(row.get("purchases7d"))

        row["spend"] = spend
        row["sales"] = sales
        row["orders"] = orders
        row["acos"] = round(spend / sales * 100, 2) if sales > 0 else None
        row["roas"] = round(sales / spend, 2) if spend > 0 else None
        row["ctr"] = round(clicks / impressions * 100, 2) if impressions > 0 else None
        row["cpc"] = round(spend / clicks, 2) if clicks > 0 else None
        row["conversionRate"] = round(orders / clicks * 100, 2) if clicks > 0 else None

        enriched.append(row)

    return enriched


def summarize(rows):
    total_spend = sum(money(r.get("cost")) for r in rows)
    total_sales = sum(money(r.get("sales7d")) for r in rows)
    total_clicks = sum(integer(r.get("clicks")) for r in rows)
    total_impressions = sum(integer(r.get("impressions")) for r in rows)
    total_orders = sum(integer(r.get("purchases7d")) for r in rows)

    return {
        "spend": round(total_spend, 2),
        "sales": round(total_sales, 2),
        "acos": round(total_spend / total_sales * 100, 2) if total_sales > 0 else None,
        "roas": round(total_sales / total_spend, 2) if total_spend > 0 else None,
        "impressions": total_impressions,
        "clicks": total_clicks,
        "ctr": round(total_clicks / total_impressions * 100, 2) if total_impressions > 0 else None,
        "cpc": round(total_spend / total_clicks, 2) if total_clicks > 0 else None,
        "orders": total_orders,
        "conversionRate": round(total_orders / total_clicks * 100, 2) if total_clicks > 0 else None,
    }


def build_dashboard_analysis(campaign_rows, search_term_rows):
    campaigns = enrich_rows(campaign_rows)
    search_terms = enrich_rows(search_term_rows)

    summary = summarize(campaigns)

    alerts = {
        "highSpendNoSalesCampaigns": sorted(
            [r for r in campaigns if r["spend"] >= 5 and r["sales"] == 0],
            key=lambda r: r["spend"],
            reverse=True,
        )[:10],
        "highAcosCampaigns": sorted(
            [r for r in campaigns if r["acos"] is not None and r["acos"] >= 40],
            key=lambda r: r["acos"],
            reverse=True,
        )[:10],
        "wastedSearchTerms": sorted(
            [r for r in search_terms if r["spend"] >= 3 and r["sales"] == 0],
            key=lambda r: r["spend"],
            reverse=True,
        )[:25],
    }

    opportunities = {
        "bestCampaigns": sorted(
            [r for r in campaigns if r["sales"] > 0],
            key=lambda r: r["sales"],
            reverse=True,
        )[:10],
        "strongSearchTerms": sorted(
            [r for r in search_terms if r["sales"] > 0 and r["roas"] is not None],
            key=lambda r: r["roas"],
            reverse=True,
        )[:25],
    }

    recommendations = [
        {
            "priority": "High",
            "type": "Waste reduction",
            "recommendation": "Review campaigns and search terms with spend but no sales.",
        },
        {
            "priority": "High",
            "type": "ACOS control",
            "recommendation": "Reduce bids on campaigns above target ACOS.",
        },
        {
            "priority": "Medium",
            "type": "Keyword harvesting",
            "recommendation": "Move strong converting search terms into exact-match campaigns.",
        },
    ]

    health_score = 100

    if summary.get("acos") and summary["acos"] > 40:
        health_score -= 25
    if len(alerts["highSpendNoSalesCampaigns"]) > 0:
        health_score -= 15
    if len(alerts["wastedSearchTerms"]) > 5:
        health_score -= 15

    health_score = max(0, health_score)

    return {
        "summary": summary,
        "alerts": alerts,
        "opportunities": opportunities,
        "recommendations": recommendations,
        "health_score": health_score,
        "campaigns": campaigns,
        "search_terms": search_terms,
    }
