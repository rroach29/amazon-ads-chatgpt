from database import SessionLocal
from models import CampaignDailyDetail, SearchTermDailyDetail
from decision_history import save_decisions_to_history


# =========================
# Decision thresholds
# =========================

HARVEST_MIN_CLICKS = 10
HARVEST_MIN_ORDERS = 2
HARVEST_MIN_SALES = 20
HARVEST_MAX_ACOS = 0.30

REDUCE_BID_MIN_SPEND = 10
REDUCE_BID_MIN_CLICKS = 10
REDUCE_BID_MIN_ORDERS = 1
REDUCE_BID_MIN_ACOS = 0.40


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


def safe_float(value):
    return float(value or 0)


def safe_int(value):
    return int(value or 0)


def risk_from_confidence(confidence):
    if confidence >= 90:
        return "LOW"
    if confidence >= 75:
        return "MEDIUM"
    return "HIGH"


# =========================
# Confidence scoring
# =========================

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


# =========================
# Helpers
# =========================

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


def suggested_bid_reduction_percent(acos):
    if acos >= 0.80:
        return 30

    if acos >= 0.60:
        return 25

    if acos >= 0.40:
        return 20

    return 15


def sort_decisions(decisions):
    decisions.sort(
        key=lambda d: (
            d["priority"] != "HIGH",
            -d["confidence"],
            -d["estimated_monthly_impact"],
        )
    )
    return decisions


# =========================
# Pause campaign decisions
# =========================

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
            spend = safe_float(row.spend)
            clicks = safe_int(row.clicks)
            sales = safe_float(row.sales)

            confidence = calculate_pause_confidence(row)
            estimated_impact = round(spend * 30, 2)
            risk = risk_from_confidence(confidence)

            reasoning = [
                f"Campaign spent ${spend:.2f}.",
                f"Campaign generated {clicks} clicks.",
                f"Campaign generated ${sales:.2f} in attributed sales.",
                "Campaign meets the pause threshold for spend, clicks, and zero sales.",
            ]

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
                        "orders": safe_int(row.orders),
                        "acos": row.acos,
                        "roas": row.roas,
                    },
                )
            )

        return {
            "status": "OK",
            "decision_type": "PAUSE_CAMPAIGN",
            "count": len(decisions),
            "decisions": sort_decisions(decisions),
        }

    finally:
        db.close()


# =========================
# Negative keyword decisions
# =========================

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

            reasoning = [
                f"Search term spent ${spend:.2f}.",
                f"Search term generated {clicks} clicks.",
                f"Search term generated ${sales:.2f} in attributed sales.",
                "Search term meets the negative keyword threshold for spend, clicks, and zero sales.",
            ]

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


# =========================
# Harvest keyword decisions
# =========================

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

            reasoning = [
                f'Search term "{search_term}" generated {orders} orders.',
                f"Search term generated {clicks} clicks.",
                f"Search term generated ${sales:.2f} in attributed sales.",
                f"Search term spent ${spend:.2f}.",
                f"Search term ACOS was {acos * 100:.1f}%.",
                "Search term meets the harvest threshold for clicks, orders, sales, and ACOS.",
                "Adding it as Exact Match should improve control, bidding, and scaling.",
            ]

            decisions.append(
                make_decision(
                    decision="HARVEST_KEYWORD",
                    priority=priority,
                    confidence=confidence,
                    risk=risk,
                    estimated_monthly_impact=estimated_impact,
                    reasoning=reasoning,
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


# =========================
# Reduce bid decisions
# =========================

def get_reduce_bid_decisions(limit=25):
    db = SessionLocal()

    try:
        rows = (
            db.query(SearchTermDailyDetail)
            .filter(SearchTermDailyDetail.channel == "amazon_ads")
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

            reasoning = [
                f'Search term "{search_term}" generated sales but is inefficient.',
                f"Spend was ${spend:.2f}.",
                f"Sales were ${sales:.2f}.",
                f"Orders were {orders}.",
                f"Clicks were {clicks}.",
                f"ACOS was {acos * 100:.1f}%.",
                f"A {reduction_percent}% bid reduction should lower spend while keeping the term active.",
            ]

            decisions.append(
                make_decision(
                    decision="REDUCE_BID",
                    priority=priority,
                    confidence=confidence,
                    risk=risk,
                    estimated_monthly_impact=estimated_impact,
                    reasoning=reasoning,
                    recommended_action=(
                        f'Reduce bid by {reduction_percent}% for '
                        f'"{search_term}" in {row.campaign_name}.'
                    ),
                    payload={
                        "campaign_id": row.campaign_id,
                        "campaign_name": row.campaign_name,
                        "ad_group_id": row.ad_group_id,
                        "ad_group_name": row.ad_group_name,
                        "search_term": search_term,
                        "keyword": row.keyword,
                        "match_type": row.match_type,
                        "suggested_bid_reduction_percent": reduction_percent,
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


# =========================
# Main decision builder
# =========================

def build_decisions():
    pause_decisions = get_pause_campaign_decisions()
    negative_decisions = get_negative_keyword_decisions()
    harvest_decisions = get_harvest_keyword_decisions()
    reduce_bid_decisions = get_reduce_bid_decisions()

    decisions = []
    decisions.extend(pause_decisions["decisions"])
    decisions.extend(negative_decisions["decisions"])
    decisions.extend(harvest_decisions["decisions"])
    decisions.extend(reduce_bid_decisions["decisions"])

    decisions = sort_decisions(decisions)

    history_result = save_decisions_to_history(decisions)

    return {
        "status": "OK",
        "count": len(decisions),
        "history_saved": history_result["saved"],
        "breakdown": {
            "pause_campaigns": pause_decisions["count"],
            "negative_keywords": negative_decisions["count"],
            "harvest_keywords": harvest_decisions["count"],
            "reduce_bids": reduce_bid_decisions["count"],
        },
        "decisions": decisions,
    }
