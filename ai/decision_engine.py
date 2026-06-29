from database import SessionLocal
from models import CampaignDailyDetail


def make_decision(
    decision,
    priority,
    confidence,
    risk,
    estimated_monthly_impact,
    reasoning,
    recommended_action,
    payload,
):
    return {
        "decision": decision,
        "priority": priority,
        "confidence": confidence,
        "risk": risk,
        "estimated_monthly_impact": estimated_monthly_impact,
        "reasoning": reasoning,
        "recommended_action": recommended_action,
        "payload": payload,
    }


def calculate_pause_confidence(row):
    confidence = 50

    if (row.clicks or 0) >= 20:
        confidence += 15

    if (row.clicks or 0) >= 30:
        confidence += 10

    if (row.spend or 0) >= 25:
        confidence += 15

    if (row.spend or 0) >= 40:
        confidence += 10

    if (row.sales or 0) == 0:
        confidence += 20

    return min(confidence, 99)


def get_pause_campaign_decisions(min_spend=25, min_clicks=20, limit=20):
    db = SessionLocal()

    try:
        rows = (
            db.query(CampaignDailyDetail)
            .filter(CampaignDailyDetail.channel == "amazon_ads")
            .filter(CampaignDailyDetail.spend >= min_spend)
            .filter(CampaignDailyDetail.clicks >= min_clicks)
            .filter(CampaignDailyDetail.sales == 0)
            .order_by(CampaignDailyDetail.spend.desc())
            .limit(limit)
            .all()
        )

        decisions = []

        for row in rows:
            spend = row.spend or 0
            clicks = row.clicks or 0
            sales = row.sales or 0

            confidence = calculate_pause_confidence(row)
            estimated_impact = round(spend * 30, 2)

            reasoning = [
                f"Campaign spent ${spend:.2f}.",
                f"Campaign generated {clicks} clicks.",
                f"Campaign generated ${sales:.2f} in attributed sales.",
                "Campaign meets the pause threshold for spend, clicks, and zero sales.",
            ]

            if confidence >= 90:
                risk = "LOW"
            elif confidence >= 75:
                risk = "MEDIUM"
            else:
                risk = "HIGH"

            decisions.append(
                make_decision(
                    decision="PAUSE_CAMPAIGN",
                    priority="HIGH",
                    confidence=confidence,
                    risk=risk,
                    estimated_monthly_impact=estimated_impact,
                    reasoning=reasoning,
                    recommended_action=f"Pause campaign: {row.campaign_name}",
                    payload={
                        "campaign_id": row.campaign_id,
                        "campaign_name": row.campaign_name,
                        "spend": spend,
                        "clicks": clicks,
                        "sales": sales,
                        "orders": row.orders or 0,
                        "acos": row.acos,
                        "roas": row.roas,
                    },
                )
            )

        decisions.sort(
            key=lambda d: (
                d["priority"] != "HIGH",
                -d["confidence"],
                -d["estimated_monthly_impact"],
            )
        )

        return {
            "status": "OK",
            "decision_type": "PAUSE_CAMPAIGN",
            "count": len(decisions),
            "decisions": decisions,
        }

    finally:
        db.close()


def build_decisions():
    pause_decisions = get_pause_campaign_decisions()

    return {
        "status": "OK",
        "count": pause_decisions["count"],
        "decisions": pause_decisions["decisions"],
    }
