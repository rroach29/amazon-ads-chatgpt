from database import SessionLocal
from models import SearchTermDailyDetail
from ai.decisions.shared import (
    make_decision,
    safe_float,
    safe_int,
    risk_from_confidence,
    sort_decisions,
)


HARVEST_MIN_CLICKS = 10
HARVEST_MIN_ORDERS = 2
HARVEST_MIN_SALES = 20
HARVEST_MAX_ACOS = 0.30


def choose_exact_campaign(source_campaign):
    if not source_campaign:
        return None

    name = source_campaign.upper()

    if "PET PHOTO" in name:
        return "PET PHOTO - EXACT"

    if "PET MEMORIAL" in name:
        return "PET - EXACT WINNERS"

    if "PET -" in name or "PET " in name:
        return "PET - EXACT WINNERS"

    if "CALVIN" in name:
        return "CALVIN - EXACT"

    return None


def calculate_harvest_keyword_confidence(clicks, orders, sales, spend, acos):
    confidence = 65

    if clicks >= 10:
        confidence += 10
    if clicks >= 20:
        confidence += 5
    if orders >= 2:
        confidence += 10
    if orders >= 3:
        confidence += 5
    if sales >= 50:
        confidence += 5
    if acos <= 0.30:
        confidence += 5
    if acos <= 0.20:
        confidence += 5

    return min(confidence, 99)


def get_harvest_keyword_decisions(limit=25):
    db = SessionLocal()

    try:
        rows = (
            db.query(SearchTermDailyDetail)
            .filter(SearchTermDailyDetail.channel == "amazon_ads")
            .filter(SearchTermDailyDetail.clicks >= HARVEST_MIN_CLICKS)
            .filter(SearchTermDailyDetail.orders >= HARVEST_MIN_ORDERS)
            .filter(SearchTermDailyDetail.sales >= HARVEST_MIN_SALES)
            .filter(SearchTermDailyDetail.sales > 0)
            .order_by(SearchTermDailyDetail.sales.desc())
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

            if acos > HARVEST_MAX_ACOS:
                continue

            target_campaign = choose_exact_campaign(row.campaign_name)

            if not target_campaign:
                continue

            confidence = calculate_harvest_keyword_confidence(
                clicks=clicks,
                orders=orders,
                sales=sales,
                spend=spend,
                acos=acos,
            )

            risk = risk_from_confidence(confidence)
            priority = "HIGH" if confidence >= 85 else "MEDIUM"
            estimated_impact = round(sales * 0.30, 2)

            decisions.append(
                make_decision(
                    decision="HARVEST_KEYWORD",
                    priority=priority,
                    confidence=confidence,
                    risk=risk,
                    estimated_monthly_impact=estimated_impact,
                    reasoning=[
                        f'Search term "{search_term}" generated {orders} orders.',
                        f"Search term generated {clicks} clicks.",
                        f"Search term generated ${sales:.2f} in attributed sales.",
                        f"Search term spent ${spend:.2f}.",
                        f"Search term ACOS was {acos * 100:.1f}%.",
                        "Search term meets the harvest threshold for clicks, orders, sales, and ACOS.",
                        "Adding it as Exact Match should improve control, bidding, and scaling.",
                    ],
                    recommended_action=(
                        f'Add "{search_term}" as an Exact Match keyword '
                        f"to campaign: {target_campaign}"
                    ),
                    payload={
                        "search_term": search_term,
                        "keyword": search_term,
                        "match_type": "EXACT",
                        "source_campaign_id": row.campaign_id,
                        "source_campaign_name": row.campaign_name,
                        "source_ad_group_id": row.ad_group_id,
                        "source_ad_group_name": row.ad_group_name,
                        "target_campaign_name": target_campaign,
                        "suggested_bid": 0.85,
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
            "decision_type": "HARVEST_KEYWORD",
            "count": len(decisions),
            "decisions": sort_decisions(decisions),
        }

    finally:
        db.close()
