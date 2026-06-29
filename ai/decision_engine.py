from database import SessionLocal
from models import CampaignDailyDetail, SearchTermDailyDetail


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

def calculate_negative_keyword_confidence(row):
    confidence = 50

    if (row.clicks or 0) >= 10:
        confidence += 15

    if (row.clicks or 0) >= 20:
        confidence += 10

    if (row.spend or 0) >= 10:
        confidence += 15

    if (row.spend or 0) >= 20:
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
            spend = row.spend or 0
            clicks = row.clicks or 0
            sales = row.sales or 0

            confidence = calculate_negative_keyword_confidence(row)
            estimated_impact = round(spend * 30, 2)

            reasoning = [
                f"Search term spent ${spend:.2f}.",
                f"Search term generated {clicks} clicks.",
                f"Search term generated ${sales:.2f} in attributed sales.",
                "Search term meets the negative keyword threshold for spend, clicks, and zero sales.",
            ]

            if confidence >= 90:
                risk = "LOW"
            elif confidence >= 75:
                risk = "MEDIUM"
            else:
                risk = "HIGH"

            decisions.append(
                make_decision(
                    decision="ADD_NEGATIVE_KEYWORD",
                    priority="HIGH",
                    confidence=confidence,
                    risk=risk,
                    estimated_monthly_impact=estimated_impact,
                    reasoning=reasoning,
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
            "decision_type": "ADD_NEGATIVE_KEYWORD",
            "count": len(decisions),
            "decisions": decisions,
        }

    finally:
        db.close()

def build_decisions():
    pause_decisions = get_pause_campaign_decisions()
    negative_decisions = get_negative_keyword_decisions()

    decisions = []
    decisions.extend(pause_decisions["decisions"])
    decisions.extend(negative_decisions["decisions"])

    decisions.sort(
        key=lambda d: (
            d["priority"] != "HIGH",
            -d["confidence"],
            -d["estimated_monthly_impact"],
        )
    )

    return {
        "status": "OK",
        "count": len(decisions),
        "breakdown": {
            "pause_campaigns": pause_decisions["count"],
            "negative_keywords": negative_decisions["count"],
        },
        "decisions": decisions,
    }
