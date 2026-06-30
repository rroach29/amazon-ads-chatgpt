from database import SessionLocal
from models import CampaignDailyDetail
from business_data_context import resolve_data_context, apply_date_context, apply_marketplace_context
from ai.decisions.shared import (
    make_decision,
    safe_float,
    safe_int,
    risk_from_confidence,
    sort_decisions,
)


INCREASE_BUDGET_MIN_SPEND = 10
INCREASE_BUDGET_MIN_ORDERS = 1
INCREASE_BUDGET_MAX_ACOS = 0.30
INCREASE_BUDGET_MIN_ROAS = 3


def calculate_increase_budget_confidence(spend, sales, orders, acos, roas):
    confidence = 65

    if spend >= 10:
        confidence += 5
    if orders >= 1:
        confidence += 5
    if orders >= 2:
        confidence += 5
    if acos <= 0.30:
        confidence += 10
    if acos <= 0.20:
        confidence += 5
    if roas >= 3:
        confidence += 5
    if roas >= 5:
        confidence += 5

    return min(confidence, 99)


def suggested_budget_increase_percent(acos):
    if acos <= 0.15:
        return 50

    if acos <= 0.25:
        return 35

    return 25


def get_increase_budget_decisions(limit=20, data_context=None, country_code=None, profile_id=None):
    db = SessionLocal()

    try:
        context = data_context or resolve_data_context(
            window="latest",
            country_code=country_code,
            profile_id=profile_id,
        )

        query = (
            db.query(CampaignDailyDetail)
            .filter(CampaignDailyDetail.channel == "amazon_ads")
            .filter(CampaignDailyDetail.profile_id.isnot(None))
            .filter(CampaignDailyDetail.country_code.isnot(None))
            .filter(CampaignDailyDetail.spend >= INCREASE_BUDGET_MIN_SPEND)
            .filter(CampaignDailyDetail.orders >= INCREASE_BUDGET_MIN_ORDERS)
            .filter(CampaignDailyDetail.sales > 0)
        )

        query = apply_date_context(query, CampaignDailyDetail, context)
        query = apply_marketplace_context(query, CampaignDailyDetail, context)

        rows = (
            query
            .order_by(CampaignDailyDetail.sales.desc())
            .limit(limit)
            .all()
        )

        decisions = []

        for row in rows:
            spend = safe_float(row.spend)
            sales = safe_float(row.sales)
            orders = safe_int(row.orders)
            clicks = safe_int(row.clicks)

            if sales <= 0 or spend <= 0:
                continue

            acos = spend / sales
            roas = sales / spend

            if acos > INCREASE_BUDGET_MAX_ACOS:
                continue

            if roas < INCREASE_BUDGET_MIN_ROAS:
                continue

            increase_percent = suggested_budget_increase_percent(acos)

            confidence = calculate_increase_budget_confidence(
                spend=spend,
                sales=sales,
                orders=orders,
                acos=acos,
                roas=roas,
            )

            risk = risk_from_confidence(confidence)
            priority = "HIGH" if confidence >= 85 else "MEDIUM"
            estimated_impact = round(sales * (increase_percent / 100), 2)

            decisions.append(
                make_decision(
                    decision="INCREASE_BUDGET",
                    priority=priority,
                    confidence=confidence,
                    risk=risk,
                    estimated_monthly_impact=estimated_impact,
                    reasoning=[
                        f"Data window: {context.get('start_date')} to {context.get('end_date')}.",
                        f"Campaign {row.campaign_name} is performing efficiently.",
                        f"Spend was ${spend:.2f}.",
                        f"Sales were ${sales:.2f}.",
                        f"Orders were {orders}.",
                        f"Clicks were {clicks}.",
                        f"ACOS was {acos * 100:.1f}%.",
                        f"ROAS was {roas:.2f}.",
                        f"A {increase_percent}% budget increase may capture additional profitable sales.",
                    ],
                    recommended_action=(
                        f"Increase budget by {increase_percent}% for "
                        f"{row.campaign_name}."
                    ),
                    payload={
                        "campaign_id": str(row.campaign_id),
                        "campaign_name": row.campaign_name,
                        "profile_id": row.profile_id,
                        "country_code": row.country_code,
                        "marketplace": row.marketplace,
                        "currency": row.currency,
                        "data_window": context,
                        "suggested_budget_increase_percent": increase_percent,
                        "increase_percent": increase_percent,
                        "spend": spend,
                        "clicks": clicks,
                        "sales": sales,
                        "orders": orders,
                        "acos": round(acos, 4),
                        "roas": round(roas, 4),
                    },
                )
            )

        return {
            "status": "OK",
            "decision_type": "INCREASE_BUDGET",
            "data_context": context,
            "count": len(decisions),
            "decisions": sort_decisions(decisions),
        }

    finally:
        db.close()
