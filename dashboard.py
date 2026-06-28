from datetime import date

from database import SessionLocal
from models import DailyDashboard
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

    db = SessionLocal()
    today = date.today()

    existing = (
        db.query(DailyDashboard)
        .filter(DailyDashboard.date == today)
        .filter(DailyDashboard.channel == "amazon_ads")
        .first()
    )

    if existing:
        existing.spend = analysis["summary"]["spend"]
        existing.sales = analysis["summary"]["sales"]
        existing.acos = analysis["summary"]["acos"]
        existing.roas = analysis["summary"]["roas"]
        existing.clicks = analysis["summary"]["clicks"]
        existing.impressions = analysis["summary"]["impressions"]
        existing.orders = analysis["summary"]["orders"]
        existing.health_score = analysis["health_score"]
        existing.alerts = analysis["alerts"]
        existing.recommendations = analysis["recommendations"]
    else:
        dashboard = DailyDashboard(
            date=today,
            channel="amazon_ads",
            spend=analysis["summary"]["spend"],
            sales=analysis["summary"]["sales"],
            acos=analysis["summary"]["acos"],
            roas=analysis["summary"]["roas"],
            clicks=analysis["summary"]["clicks"],
            impressions=analysis["summary"]["impressions"],
            orders=analysis["summary"]["orders"],
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
        "summary": analysis["summary"],
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
