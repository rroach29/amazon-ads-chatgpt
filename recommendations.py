from database import SessionLocal
from models import CampaignDailyDetail, SearchTermDailyDetail, OptimizationQueue
from datetime import datetime

def make_recommendation(priority, action_type, title, reason, data=None):
    return {
        "priority": priority,
        "type": action_type,
        "title": title,
        "reason": reason,
        "data": data or {},
    }


def get_pause_campaigns(db, min_spend=25, min_clicks=20):
    rows = (
        db.query(CampaignDailyDetail)
        .filter(CampaignDailyDetail.channel == "amazon_ads")
        .filter(CampaignDailyDetail.spend >= min_spend)
        .filter(CampaignDailyDetail.clicks >= min_clicks)
        .filter(CampaignDailyDetail.sales == 0)
        .order_by(CampaignDailyDetail.spend.desc())
        .limit(10)
        .all()
    )

    return [
        make_recommendation(
            "HIGH",
            "PAUSE_CAMPAIGN",
            f"Pause {row.campaign_name}",
            f"Spent ${row.spend:.2f} with {row.clicks} clicks and no sales.",
            {
                "campaign_id": row.campaign_id,
                "campaign_name": row.campaign_name,
                "spend": row.spend,
                "clicks": row.clicks,
                "sales": row.sales,
            },
        )
        for row in rows
    ]


def get_scale_campaigns(db, max_acos=25, min_orders=2):
    rows = (
        db.query(CampaignDailyDetail)
        .filter(CampaignDailyDetail.channel == "amazon_ads")
        .filter(CampaignDailyDetail.orders >= min_orders)
        .filter(CampaignDailyDetail.acos <= max_acos)
        .filter(CampaignDailyDetail.sales > 0)
        .order_by(CampaignDailyDetail.sales.desc())
        .limit(10)
        .all()
    )

    return [
        make_recommendation(
            "MEDIUM",
            "SCALE_CAMPAIGN",
            f"Scale {row.campaign_name}",
            f"Generated ${row.sales:.2f} in sales at {row.acos:.1f}% ACOS.",
            {
                "campaign_id": row.campaign_id,
                "campaign_name": row.campaign_name,
                "sales": row.sales,
                "orders": row.orders,
                "acos": row.acos,
                "roas": row.roas,
            },
        )
        for row in rows
    ]


def get_negative_search_terms(db, min_spend=15, min_clicks=15):
    rows = (
        db.query(SearchTermDailyDetail)
        .filter(SearchTermDailyDetail.channel == "amazon_ads")
        .filter(SearchTermDailyDetail.spend >= min_spend)
        .filter(SearchTermDailyDetail.clicks >= min_clicks)
        .filter(SearchTermDailyDetail.sales == 0)
        .order_by(SearchTermDailyDetail.spend.desc())
        .limit(20)
        .all()
    )

    return [
        make_recommendation(
            "HIGH",
            "ADD_NEGATIVE_KEYWORD",
            f"Add negative for '{row.search_term}'",
            f"Search term spent ${row.spend:.2f} with {row.clicks} clicks and no sales.",
            {
                "campaign_id": row.campaign_id,
                "campaign_name": row.campaign_name,
                "ad_group_id": row.ad_group_id,
                "ad_group_name": row.ad_group_name,
                "search_term": row.search_term,
                "spend": row.spend,
                "clicks": row.clicks,
                "sales": row.sales,
                "suggested_negative_match_type": "negative phrase",
            },
        )
        for row in rows
    ]


def get_harvest_keywords(db, max_acos=30, min_orders=2):
    rows = (
        db.query(SearchTermDailyDetail)
        .filter(SearchTermDailyDetail.channel == "amazon_ads")
        .filter(SearchTermDailyDetail.orders >= min_orders)
        .filter(SearchTermDailyDetail.acos <= max_acos)
        .filter(SearchTermDailyDetail.sales > 0)
        .order_by(SearchTermDailyDetail.sales.desc())
        .limit(20)
        .all()
    )

    return [
        make_recommendation(
            "MEDIUM",
            "HARVEST_KEYWORD",
            f"Harvest '{row.search_term}' into Exact Match",
            f"Search term has {row.orders} orders and {row.acos:.1f}% ACOS.",
            {
                "campaign_id": row.campaign_id,
                "campaign_name": row.campaign_name,
                "ad_group_id": row.ad_group_id,
                "ad_group_name": row.ad_group_name,
                "search_term": row.search_term,
                "keyword": row.keyword,
                "match_type": row.match_type,
                "sales": row.sales,
                "orders": row.orders,
                "acos": row.acos,
                "suggested_match_type": "exact",
            },
        )
        for row in rows
    ]


def get_reduce_bid_terms(db, min_spend=20, min_acos=70):
    rows = (
        db.query(SearchTermDailyDetail)
        .filter(SearchTermDailyDetail.channel == "amazon_ads")
        .filter(SearchTermDailyDetail.spend >= min_spend)
        .filter(SearchTermDailyDetail.acos >= min_acos)
        .filter(SearchTermDailyDetail.sales > 0)
        .order_by(SearchTermDailyDetail.acos.desc())
        .limit(20)
        .all()
    )

    return [
        make_recommendation(
            "MEDIUM",
            "REDUCE_BID",
            f"Reduce bid pressure on '{row.search_term}'",
            f"Search term is converting, but ACOS is high at {row.acos:.1f}%.",
            {
                "campaign_id": row.campaign_id,
                "campaign_name": row.campaign_name,
                "ad_group_id": row.ad_group_id,
                "ad_group_name": row.ad_group_name,
                "search_term": row.search_term,
                "spend": row.spend,
                "sales": row.sales,
                "orders": row.orders,
                "acos": row.acos,
                "suggested_bid_change": "-20%",
            },
        )
        for row in rows
    ]


def build_recommendations():
    db = SessionLocal()

    try:
        recommendations = []
        recommendations.extend(get_pause_campaigns(db))
        recommendations.extend(get_negative_search_terms(db))
        recommendations.extend(get_harvest_keywords(db))
        recommendations.extend(get_scale_campaigns(db))
        recommendations.extend(get_reduce_bid_terms(db))

        priority_order = {"HIGH": 1, "MEDIUM": 2, "LOW": 3}

        recommendations.sort(
            key=lambda r: priority_order.get(r["priority"], 99)
        )

        return {
    "status": "OK",
    "count": len(recommendations),
    "queue_saved": queue_result["saved"],
    "recommendations": recommendations,
}

    finally:
        db.close()
        def save_recommendations_to_queue(recommendations):
    db = SessionLocal()

    try:
        saved = []

        for rec in recommendations:
            data = rec.get("data", {})

            exists = (
                db.query(OptimizationQueue)
                .filter(OptimizationQueue.status == "PENDING")
                .filter(OptimizationQueue.recommendation_type == rec.get("type"))
                .filter(OptimizationQueue.campaign_id == data.get("campaign_id"))
                .filter(OptimizationQueue.search_term == data.get("search_term"))
                .first()
            )

            if exists:
                continue

            item = OptimizationQueue(
                channel="amazon_ads",
                status="PENDING",
                priority=rec.get("priority"),
                recommendation_type=rec.get("type"),
                campaign_id=data.get("campaign_id"),
                campaign_name=data.get("campaign_name"),
                ad_group_id=data.get("ad_group_id"),
                ad_group_name=data.get("ad_group_name"),
                search_term=data.get("search_term"),
                keyword=data.get("keyword"),
                title=rec.get("title"),
                reason=rec.get("reason"),
                recommended_action=rec.get("type"),
                confidence=rec.get("confidence", 80),
                estimated_monthly_savings=data.get("spend", 0) * 30,
                payload=rec,
            )

            db.add(item)
            saved.append(item)

        db.commit()

        return {
            "status": "OK",
            "saved": len(saved),
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()
