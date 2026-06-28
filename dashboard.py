from datetime import date

from database import SessionLocal
from models import DailyDashboard, CampaignDailyDetail, SearchTermDailyDetail
from amazon_ads import download_report_data
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

    db.query(CampaignDailyDetail).filter(
        CampaignDailyDetail.date == today,
        CampaignDailyDetail.channel == "amazon_ads",
    ).delete()

    db.query(SearchTermDailyDetail).filter(
        SearchTermDailyDetail.date == today,
        SearchTermDailyDetail.channel == "amazon_ads",
    ).delete()

    for r in campaigns:
        db.add(CampaignDailyDetail(
            date=today,
            channel="amazon_ads",
            campaign_id=str(r.get("campaignId")),
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
        ))

    for r in search_terms:
        db.add(SearchTermDailyDetail(
            date=today,
            channel="amazon_ads",
            campaign_id=str(r.get("campaignId")),
            campaign_name=r.get("campaignName"),
            ad_group_id=str(r.get("adGroupId")),
            ad_group_name=r.get("adGroupName"),
            keyword_id=str(r.get("keywordId")),
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
        ))

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
        dashboard = DailyDashboard(
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
        db.add(dashboard)

    db.commit()
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

    latest = (
        db.query(DailyDashboard)
        .order_by(DailyDashboard.date.desc())
        .first()
    )

    db.close()

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


def get_dashboard_history(days: int = 30):
    db = SessionLocal()

    rows = (
        db.query(DailyDashboard)
        .filter(DailyDashboard.channel == "amazon_ads")
        .order_by(DailyDashboard.date.desc())
        .limit(days)
        .all()
    )

    db.close()

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
