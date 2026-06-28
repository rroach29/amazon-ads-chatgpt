from datetime import date

from database import SessionLocal
from models import DailyDashboard, CampaignDailyDetail, SearchTermDailyDetail
from amazon.reports import download_report_data
from analytics import build_dashboard_analysis


def save_dashboard_from_reports(campaign_report_id: str, search_term_report_id: str):
    campaign_download = download_report_data(campaign_report_id)
    search_download = download_report_data(search_term_report_id)

    if not campaign_download.get("ready") or not search_download.get("ready"):
        return {
            "status": "PENDING",
            "message": "One or both reports are not ready yet.",
            "campaignStatus": campaign_download.get("status"),
            "searchTermStatus": search_download.get("status"),
        }

    analysis = build_dashboard_analysis(
        campaign_download.get("data", []),
        search_download.get("data", []),
    )

    campaigns = analysis["campaigns"]
    search_terms = analysis["search_terms"]
    summary = analysis["summary"]
    today = date.today()

    db = SessionLocal()

    try:
        db.query(CampaignDailyDetail).filter(
            CampaignDailyDetail.date == today,
            CampaignDailyDetail.channel == "amazon_ads",
        ).delete()

        db.query(SearchTermDailyDetail).filter(
            SearchTermDailyDetail.date == today,
            SearchTermDailyDetail.channel == "amazon_ads",
        ).delete()

        for r in campaigns:
            db.add(
                CampaignDailyDetail(
                    date=today,
                    channel="amazon_ads",
                    campaign_id=str(r.get("campaignId") or ""),
                    campaign_name=r.get("campaignName"),
                    campaign_status=r.get("campaignStatus"),
                    impressions=r.get("impressions", 0),
                    clicks=r.get("clicks", 0),
                    spend=r.get("spend", 0),
                    sales=r.get("sales", 0),
                    orders=r.get("orders", 0),
                    acos=r.get("acos"),
                    roas=r.get("roas"),
                    ctr=r.get("ctr"),
                    cpc=r.get("cpc"),
                    conversion_rate=r.get("conversionRate"),
                    raw=r,
                )
            )

        for r in search_terms:
            db.add(
                SearchTermDailyDetail(
                    date=today,
                    channel="amazon_ads",
                    campaign_id=str(r.get("campaignId") or ""),
                    campaign_name=r.get("campaignName"),
                    ad_group_id=str(r.get("adGroupId") or ""),
                    ad_group_name=r.get("adGroupName"),
                    keyword_id=str(r.get("keywordId") or ""),
                    keyword=r.get("keyword"),
                    match_type=r.get("matchType"),
                    search_term=r.get("searchTerm"),
                    impressions=r.get("impressions", 0),
                    clicks=r.get("clicks", 0),
                    spend=r.get("spend", 0),
                    sales=r.get("sales", 0),
                    orders=r.get("orders", 0),
                    acos=r.get("acos"),
                    roas=r.get("roas"),
                    ctr=r.get("ctr"),
                    cpc=r.get("cpc"),
                    conversion_rate=r.get("conversionRate"),
                    raw=r,
                )
            )

        existing = (
            db.query(DailyDashboard)
            .filter(DailyDashboard.date == today)
            .filter(DailyDashboard.channel == "amazon_ads")
            .first()
        )

        if existing:
            existing.spend = summary["spend"]
            existing.sales = summary["sales"]
            existing.acos = summary["acos"]
            existing.roas = summary["roas"]
            existing.clicks = summary["clicks"]
            existing.impressions = summary["impressions"]
            existing.orders = summary["orders"]
            existing.health_score = analysis["health_score"]
            existing.alerts = analysis["alerts"]
            existing.recommendations = analysis["recommendations"]
        else:
            db.add(
                DailyDashboard(
                    date=today,
                    channel="amazon_ads",
                    spend=summary["spend"],
                    sales=summary["sales"],
                    acos=summary["acos"],
                    roas=summary["roas"],
                    clicks=summary["clicks"],
                    impressions=summary["impressions"],
                    orders=summary["orders"],
                    health_score=analysis["health_score"],
                    alerts=analysis["alerts"],
                    recommendations=analysis["recommendations"],
                )
            )

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    return {
        "status": "OK",
        "message": "Dashboard collected and saved.",
        "summary": summary,
        "health_score": analysis["health_score"],
        "alerts": analysis["alerts"],
        "recommendations": analysis["recommendations"],
    }


def get_latest_dashboard():
    db = SessionLocal()

    try:
        latest = (
            db.query(DailyDashboard)
            .filter(DailyDashboard.channel == "amazon_ads")
            .order_by(DailyDashboard.date.desc())
            .first()
        )

        if not latest:
            return {
                "status": "NO_DATA",
                "message": "Database is connected, but no dashboard data has been collected yet.",
            }

        return {
            "status": "OK",
            "date": str(latest.date),
            "channel": latest.channel,
            "summary": {
                "spend": latest.spend,
                "sales": latest.sales,
                "acos": latest.acos,
                "roas": latest.roas,
                "clicks": latest.clicks,
                "impressions": latest.impressions,
                "orders": latest.orders,
                "health_score": latest.health_score,
            },
            "alerts": latest.alerts,
            "recommendations": latest.recommendations,
        }

    finally:
        db.close()


def get_dashboard_history(days: int = 30):
    db = SessionLocal()

    try:
        rows = (
            db.query(DailyDashboard)
            .filter(DailyDashboard.channel == "amazon_ads")
            .order_by(DailyDashboard.date.desc())
            .limit(days)
            .all()
        )

        rows = list(reversed(rows))

        return {
            "status": "OK",
            "days": days,
            "history": [
                {
                    "date": str(row.date),
                    "spend": row.spend,
                    "sales": row.sales,
                    "acos": row.acos,
                    "roas": row.roas,
                    "clicks": row.clicks,
                    "impressions": row.impressions,
                    "orders": row.orders,
                    "health_score": row.health_score,
                }
                for row in rows
            ],
        }

    finally:
        db.close()


def serialize_campaign(row):
    return {
        "date": str(row.date),
        "channel": row.channel,
        "campaign_id": row.campaign_id,
        "campaign_name": row.campaign_name,
        "campaign_status": row.campaign_status,
        "impressions": row.impressions,
        "clicks": row.clicks,
        "spend": row.spend,
        "sales": row.sales,
        "orders": row.orders,
        "acos": row.acos,
        "roas": row.roas,
        "ctr": row.ctr,
        "cpc": row.cpc,
        "conversion_rate": row.conversion_rate,
    }


def serialize_search_term(row):
    return {
        "date": str(row.date),
        "channel": row.channel,
        "campaign_id": row.campaign_id,
        "campaign_name": row.campaign_name,
        "ad_group_id": row.ad_group_id,
        "ad_group_name": row.ad_group_name,
        "keyword_id": row.keyword_id,
        "keyword": row.keyword,
        "match_type": row.match_type,
        "search_term": row.search_term,
        "impressions": row.impressions,
        "clicks": row.clicks,
        "spend": row.spend,
        "sales": row.sales,
        "orders": row.orders,
        "acos": row.acos,
        "roas": row.roas,
        "ctr": row.ctr,
        "cpc": row.cpc,
        "conversion_rate": row.conversion_rate,
    }


def get_campaigns(limit: int = 100):
    db = SessionLocal()

    try:
        rows = (
            db.query(CampaignDailyDetail)
            .filter(CampaignDailyDetail.channel == "amazon_ads")
            .order_by(CampaignDailyDetail.date.desc(), CampaignDailyDetail.spend.desc())
            .limit(limit)
            .all()
        )

        return {
            "status": "OK",
            "count": len(rows),
            "campaigns": [serialize_campaign(row) for row in rows],
        }

    finally:
        db.close()


def get_top_campaigns(limit: int = 25):
    db = SessionLocal()

    try:
        rows = (
            db.query(CampaignDailyDetail)
            .filter(CampaignDailyDetail.channel == "amazon_ads")
            .filter(CampaignDailyDetail.sales > 0)
            .order_by(CampaignDailyDetail.sales.desc())
            .limit(limit)
            .all()
        )

        return {
            "status": "OK",
            "count": len(rows),
            "campaigns": [serialize_campaign(row) for row in rows],
        }

    finally:
        db.close()


def get_waste_campaigns(min_spend: float = 10, limit: int = 25):
    db = SessionLocal()

    try:
        rows = (
            db.query(CampaignDailyDetail)
            .filter(CampaignDailyDetail.channel == "amazon_ads")
            .filter(CampaignDailyDetail.spend >= min_spend)
            .filter(CampaignDailyDetail.sales == 0)
            .order_by(CampaignDailyDetail.spend.desc())
            .limit(limit)
            .all()
        )

        return {
            "status": "OK",
            "min_spend": min_spend,
            "count": len(rows),
            "campaigns": [serialize_campaign(row) for row in rows],
        }

    finally:
        db.close()


def get_search_terms(limit: int = 100):
    db = SessionLocal()

    try:
        rows = (
            db.query(SearchTermDailyDetail)
            .filter(SearchTermDailyDetail.channel == "amazon_ads")
            .order_by(SearchTermDailyDetail.date.desc(), SearchTermDailyDetail.spend.desc())
            .limit(limit)
            .all()
        )

        return {
            "status": "OK",
            "count": len(rows),
            "search_terms": [serialize_search_term(row) for row in rows],
        }

    finally:
        db.close()


def get_winning_search_terms(max_acos: float = 35, min_orders: int = 1, limit: int = 25):
    db = SessionLocal()

    try:
        rows = (
            db.query(SearchTermDailyDetail)
            .filter(SearchTermDailyDetail.channel == "amazon_ads")
            .filter(SearchTermDailyDetail.orders >= min_orders)
            .filter(SearchTermDailyDetail.acos <= max_acos)
            .order_by(SearchTermDailyDetail.sales.desc())
            .limit(limit)
            .all()
        )

        return {
            "status": "OK",
            "max_acos": max_acos,
            "min_orders": min_orders,
            "count": len(rows),
            "search_terms": [serialize_search_term(row) for row in rows],
        }

    finally:
        db.close()


def get_wasted_search_terms(min_spend: float = 10, limit: int = 25):
    db = SessionLocal()

    try:
        rows = (
            db.query(SearchTermDailyDetail)
            .filter(SearchTermDailyDetail.channel == "amazon_ads")
            .filter(SearchTermDailyDetail.spend >= min_spend)
            .filter(SearchTermDailyDetail.sales == 0)
            .order_by(SearchTermDailyDetail.spend.desc())
            .limit(limit)
            .all()
        )

        return {
            "status": "OK",
            "min_spend": min_spend,
            "count": len(rows),
            "search_terms": [serialize_search_term(row) for row in rows],
        }

    finally:
        db.close()
