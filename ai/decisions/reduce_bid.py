from database import SessionLocal
from models import SearchTermDailyDetail
from ai.decisions.shared import (
    make_decision,
    safe_float,
    safe_int,
    risk_from_confidence,
    sort_decisions,
)


REDUCE_BID_MIN_SPEND = 10
REDUCE_BID_MIN_CLICKS = 10
REDUCE_BID_MIN_ORDERS = 1
REDUCE_BID_MIN_ACOS = 0.40


def calculate_reduce_bid_confidence(clicks, orders, spend, sales, acos):
    confidence = 60

    if clicks >= 10:
        confidence += 10
    if clicks >= 20:
        confidence += 5
    if orders >= 1:
        confidence += 10
    if spend >= 20:
        confidence += 5
    if acos >= 0.40:
        confidence += 5
    if acos >= 0.60:
        confidence += 5

    return min(confidence, 99)


def suggested_bid_reduction_percent(acos):
    if acos >= 0.80:
        return 30

    if acos >= 0.60:
        return 25

    if acos >= 0.40:
        return 20

    return 15


def get_reduce_bid_decisions(limit=25):
    db = SessionLocal()

    try:
        rows = (
            db.query(SearchTermDailyDetail)
            .filter(SearchTermDailyDetail.channel == "amazon_ads")
            .filter(SearchTermDailyDetail.profile_id.isnot(None))
            .filter(SearchTermDailyDetail.country_code.isnot(None))
            .filter(SearchTermDailyDetail.keyword_id.isnot(None))
            .filter(SearchTermDailyDetail.spend >= REDUCE_BID_MIN_SPEND)
            .filter(SearchTermDailyDetail.clicks >= REDUCE_BID_MIN_CLICKS)
            .filter(SearchTermDailyDetail.orders >= REDUCE_BID_MIN_ORDERS)
            .filter(SearchTermDailyDetail.sales > 0)
            .order_by(SearchTermDailyDetail.acos.desc())
            .limit(limit)
            .all()
        )

        decisions = []

        for row in rows:
            search_term = row.search_term

            if not search_term:
                continue

            spend = safe_float(row.spend)
            sales = safe_float(row.sales)
            clicks = safe_int(row.clicks)
            orders = safe_int(row.orders)

            if sales <= 0:
                continue

            acos = spend / sales

            if acos < REDUCE_BID_MIN_ACOS:
                continue

            reduction_percent = suggested_bid_reduction_percent(acos)

            confidence = calculate_reduce_bid_confidence(
                clicks=clicks,
                orders=orders,
                spend=spend,
                sales=sales,
                acos=acos,
            )

            risk = risk_from_confidence(confidence)
            priority = "HIGH" if acos >= 0.60 else "MEDIUM"
            estimated_impact = round(
                spend * (reduction_percent / 100) * 30,
                2,
            )

            decisions.append(
                make_decision(
                    decision="REDUCE_BID",
                    priority=priority,
                    confidence=confidence,
                    risk=risk,
                    estimated_monthly_impact=estimated_impact,
                    reasoning=[
                        f'Search term "{search_term}" generated sales but is inefficient.',
                        f"Spend was ${spend:.2f}.",
                        f"Sales were ${sales:.2f}.",
                        f"Orders were {orders}.",
                        f"Clicks were {clicks}.",
                        f"ACOS was {acos * 100:.1f}%.",
                        f"A {reduction_percent}% bid reduction should lower spend while keeping the term active.",
                    ],
                    recommended_action=(
                        f'Reduce bid by {reduction_percent}% for '
                        f'"{search_term}" in {row.campaign_name}.'
                    ),
                    payload={
                        "campaign_id": str(row.campaign_id),
                        "campaign_name": row.campaign_name,
                        "ad_group_id": row.ad_group_id,
                        "ad_group_name": row.ad_group_name,
                        "keyword_id": str(row.keyword_id),
                        "keyword": row.keyword,
                        "match_type": row.match_type,
                        "profile_id": row.profile_id,
                        "country_code": row.country_code,
                        "marketplace": row.marketplace,
                        "currency": row.currency,
                        "search_term": search_term,
                        "suggested_bid_reduction_percent": reduction_percent,
                        "reduction_percent": reduction_percent,
                        "spend": spend,
                        "clicks": clicks,
                        "sales": sales,
                        "orders": orders,
                        "acos": round(acos, 4),
                        "roas": round(sales / spend, 4) if spend > 0 else None,
                    },
                )
            )

        return {
            "status": "OK",
            "decision_type": "REDUCE_BID",
            "count": len(decisions),
            "decisions": sort_decisions(decisions),
        }

    finally:
        db.close()
