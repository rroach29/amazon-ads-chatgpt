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


def calculate_pause_confidence(row):
    confidence = 50

    if safe_int(row.clicks) >= 20:
        confidence += 15
    if safe_int(row.clicks) >= 30:
        confidence += 10
    if safe_float(row.spend) >= 25:
        confidence += 15
    if safe_float(row.spend) >= 40:
        confidence += 10
    if safe_float(row.sales) == 0:
        confidence += 20

    return min(confidence, 99)


def get_pause_campaign_decisions(
    min_spend=25,
    min_clicks=20,
    limit=20,
    data_context=None,
    country_code=None,
    profile_id=None,
):
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
            .filter(CampaignDailyDetail.spend >= min_spend)
            .filter(CampaignDailyDetail.clicks >= min_clicks)
            .filter(CampaignDailyDetail.sales == 0)
        )

        query = apply_date_context(query, CampaignDailyDetail, context)
        query = apply_marketplace_context(query, CampaignDailyDetail, context)

        rows = (
            query
            .order_by(CampaignDailyDetail.spend.desc())
            .limit(limit)
            .all()
        )

        decisions = []

        for row in rows:
            spend = safe_float(row.spend)
            clicks = safe_int(row.clicks)
            sales = safe_float(row.sales)

            confidence = calculate_pause_confidence(row)
            estimated_impact = round(spend * 30, 2)
            risk = risk_from_confidence(confidence)

            decisions.append(
                make_decision(
                    decision="PAUSE_CAMPAIGN",
                    priority="HIGH",
                    confidence=confidence,
                    risk=risk,
                    estimated_monthly_impact=estimated_impact,
                    reasoning=[
                        f"Data window: {context.get('start_date')} to {context.get('end_date')}.",
                        f"Campaign spent ${spend:.2f}.",
                        f"Campaign generated {clicks} clicks.",
                        f"Campaign generated ${sales:.2f} in attributed sales.",
                        "Campaign meets the pause threshold for spend, clicks, and zero sales.",
                    ],
                    recommended_action=f"Pause campaign: {row.campaign_name}",
                    payload={
                        "campaign_id": str(row.campaign_id),
                        "campaign_name": row.campaign_name,
                        "profile_id": row.profile_id,
                        "country_code": row.country_code,
                        "marketplace": row.marketplace,
                        "currency": row.currency,
                        "data_window": context,
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
            "decision_type": "PAUSE_CAMPAIGN",
            "data_context": context,
            "count": len(decisions),
            "decisions": sort_decisions(decisions),
        }

    finally:
        db.close()
