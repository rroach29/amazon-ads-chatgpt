from database import SessionLocal
from models import SearchTermDailyDetail
from ai.decisions.shared import (
    make_decision,
    safe_float,
    safe_int,
    risk_from_confidence,
    sort_decisions,
)


def calculate_negative_keyword_confidence(row):
    confidence = 50

    if safe_int(row.clicks) >= 10:
        confidence += 15
    if safe_int(row.clicks) >= 20:
        confidence += 10
    if safe_float(row.spend) >= 10:
        confidence += 15
    if safe_float(row.spend) >= 20:
        confidence += 10
    if safe_float(row.sales) == 0:
        confidence += 20

    return min(confidence, 99)


def get_negative_keyword_decisions(min_spend=10, min_clicks=10, limit=25):
    db = SessionLocal()

    try:
        rows = (
            db.query(SearchTermDailyDetail)
            .filter(SearchTermDailyDetail.channel == "amazon_ads")
            .filter(SearchTermDailyDetail.spend >= min_spend)
            .filter(SearchTermDailyDetail.clicks >= min_clicks)
            .filter(SearchTermDailyDetail.sales == 0)
            .order_by(SearchTermDailyDetail.spend.desc())
            .limit(limit)
            .all()
        )

        decisions = []

        for row in rows:
            spend = safe_float(row.spend)
            clicks = safe_int(row.clicks)
            sales = safe_float(row.sales)

            confidence = calculate_negative_keyword_confidence(row)
            estimated_impact = round(spend * 30, 2)
            risk = risk_from_confidence(confidence)

            decisions.append(
                make_decision(
                    decision="ADD_NEGATIVE_KEYWORD",
                    priority="HIGH",
                    confidence=confidence,
                    risk=risk,
                    estimated_monthly_impact=estimated_impact,
                    reasoning=[
                        f"Search term spent ${spend:.2f}.",
                        f"Search term generated {clicks} clicks.",
                        f"Search term generated ${sales:.2f} in attributed sales.",
                        "Search term meets the negative keyword threshold for spend, clicks, and zero sales.",
                    ],
                    recommended_action=f"Add negative phrase: {row.search_term}",
                    payload={
                        "campaign_id": row.campaign_id,
                        "campaign_name": row.campaign_name,
                        "ad_group_id": row.ad_group_id,
                        "ad_group_name": row.ad_group_name,
                        "search_term": row.search_term,
                        "keyword": row.keyword,
                        "match_type": row.match_type,
                        "suggested_negative_match_type": "negative phrase",
                        "spend": spend,
                        "clicks": clicks,
                        "sales": sales,
                        "orders": safe_int(row.orders),
                        "acos": row.acos,
                        "roas": row.roas,
                    },
                )
            )

        return {
            "status": "OK",
            "decision_type": "ADD_NEGATIVE_KEYWORD",
            "count": len(decisions),
            "decisions": sort_decisions(decisions),
        }

    finally:
        db.close()
