from datetime import date

from database import SessionLocal
from models import DailyDashboard, CampaignDailyDetail, SearchTermDailyDetail
from amazon_ads import download_report_data
from analytics import build_dashboard_analysis
from models import CampaignDailyDetail, SearchTermDailyDetail
from datetime import date

def safe_float(value):
    try:
        if value in [None, "", "NaN"]:
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def safe_int(value):
    try:
        if value in [None, "", "NaN"]:
            return 0
        return int(float(value))
    except Exception:
        return 0

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
def save_campaign_daily_details(db, campaign_rows, report_date=None):
    if report_date is None:
        report_date = date.today()

    for row in campaign_rows:
        detail = CampaignDailyDetail(
            date=report_date,

            campaign_id=str(row.get("campaignId") or row.get("campaign_id") or ""),
            campaign_name=row.get("campaignName") or row.get("campaign_name") or "",
            campaign_status=row.get("campaignStatus") or row.get("campaign_status") or "",
            campaign_type=row.get("campaignType") or row.get("campaign_type") or "Sponsored Products",

            impressions=safe_int(row.get("impressions")),
            clicks=safe_int(row.get("clicks")),
            spend=safe_float(row.get("cost") or row.get("spend")),
            sales=safe_float(row.get("sales") or row.get("attributedSales14d")),
            orders=safe_int(row.get("orders") or row.get("purchases14d")),

            ctr=safe_float(row.get("ctr")),
            cpc=safe_float(row.get("cpc")),
            conversion_rate=safe_float(row.get("conversionRate") or row.get("conversion_rate")),
            acos=safe_float(row.get("acos")),
            roas=safe_float(row.get("roas")),
        )

        db.add(detail)

    db.commit()
def save_search_term_daily_details(db, search_term_rows, report_date=None):
    if report_date is None:
        report_date = date.today()

    for row in search_term_rows:
        detail = SearchTermDailyDetail(
            date=report_date,

            campaign_id=str(row.get("campaignId") or row.get("campaign_id") or ""),
            campaign_name=row.get("campaignName") or row.get("campaign_name") or "",
            ad_group_name=row.get("adGroupName") or row.get("ad_group_name") or "",

            search_term=row.get("searchTerm") or row.get("customerSearchTerm") or row.get("search_term") or "",
            keyword=row.get("keyword") or row.get("targeting") or "",
            match_type=row.get("matchType") or row.get("match_type") or "",

            impressions=safe_int(row.get("impressions")),
            clicks=safe_int(row.get("clicks")),
            spend=safe_float(row.get("cost") or row.get("spend")),
            sales=safe_float(row.get("sales") or row.get("attributedSales14d")),
            orders=safe_int(row.get("orders") or row.get("purchases14d")),

            ctr=safe_float(row.get("ctr")),
            cpc=safe_float(row.get("cpc")),
            conversion_rate=safe_float(row.get("conversionRate") or row.get("conversion_rate")),
            acos=safe_float(row.get("acos")),
            roas=safe_float(row.get("roas")),
        )

        db.add(detail)

    db.commit()

def get_campaigns(limit: int = 100):
    return (
        db = SessionLocal()
        db.query(CampaignDailyDetail)
        .order_by(CampaignDailyDetail.date.desc(), CampaignDailyDetail.spend.desc())
        .limit(limit)
        .all()
    )


def get_top_campaigns(limit: int = 25):
    return (
        db = SessionLocal()
        db.query(CampaignDailyDetail)
        .filter(CampaignDailyDetail.sales > 0)
        .order_by(CampaignDailyDetail.sales.desc())
        .limit(limit)
        .all()
    )


def get_waste_campaigns(min_spend: float = 10, limit: int = 25):
    return (
        db = SessionLocal()
        db.query(CampaignDailyDetail)
        .filter(CampaignDailyDetail.spend >= min_spend)
        .filter(CampaignDailyDetail.sales == 0)
        .order_by(CampaignDailyDetail.spend.desc())
        .limit(limit)
        .all()
    )


def get_search_terms(limit: int = 100):
    return (
        db = SessionLocal()
        db.query(SearchTermDailyDetail)
        .order_by(SearchTermDailyDetail.date.desc(), SearchTermDailyDetail.spend.desc())
        .limit(limit)
        .all()
    )


def get_winning_search_terms(max_acos: float = 35, min_orders: int = 1, limit: int = 25):
    return (
        db = SessionLocal()
        db.query(SearchTermDailyDetail)
        .filter(SearchTermDailyDetail.orders >= min_orders)
        .filter(SearchTermDailyDetail.acos <= max_acos)
        .order_by(SearchTermDailyDetail.sales.desc())
        .limit(limit)
        .all()
    )


def get_wasted_search_terms(min_spend: float = 10, limit: int = 25):
    return (
        db = SessionLocal()
        db.query(SearchTermDailyDetail)
        .filter(SearchTermDailyDetail.spend >= min_spend)
        .filter(SearchTermDailyDetail.sales == 0)
        .order_by(SearchTermDailyDetail.spend.desc())
        .limit(limit)
        .all()
    )

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
