import os
import json
import gzip
import re
import time
from datetime import date, timedelta
from database import engine, SessionLocal
from models import Base, DailyDashboard, ScheduledReportJob
from apscheduler.schedulers.background import BackgroundScheduler

import requests
from fastapi import FastAPI, Header, HTTPException

app = FastAPI(title="Amazon Ads ChatGPT API")

Base.metadata.create_all(bind=engine)

AMAZON_CLIENT_ID = os.getenv("AMAZON_CLIENT_ID")
AMAZON_CLIENT_SECRET = os.getenv("AMAZON_CLIENT_SECRET")
AMAZON_REFRESH_TOKEN = os.getenv("AMAZON_REFRESH_TOKEN")
AMAZON_PROFILE_ID = os.getenv("AMAZON_PROFILE_ID")
CHATGPT_API_KEY = os.getenv("CHATGPT_API_KEY")

TOKEN_URL = "https://api.amazon.com/auth/o2/token"
ADS_BASE_URL = "https://advertising-api.amazon.com"

LATEST_ANALYSIS = {
    "campaignReportId": None,
    "searchTermReportId": None,
    "createdAt": None,
}

def verify_key(x_api_key: str):
    if not CHATGPT_API_KEY:
        raise HTTPException(status_code=500, detail="CHATGPT_API_KEY is not set")
    if x_api_key != CHATGPT_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


def get_access_token():
    missing = [
        name for name, value in {
            "AMAZON_CLIENT_ID": AMAZON_CLIENT_ID,
            "AMAZON_CLIENT_SECRET": AMAZON_CLIENT_SECRET,
            "AMAZON_REFRESH_TOKEN": AMAZON_REFRESH_TOKEN,
        }.items()
        if not value
    ]

    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"Missing environment variables: {', '.join(missing)}",
        )

    r = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": AMAZON_REFRESH_TOKEN,
            "client_id": AMAZON_CLIENT_ID,
            "client_secret": AMAZON_CLIENT_SECRET,
        },
        timeout=30,
    )

    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return r.json()["access_token"]


def ads_headers():
    if not AMAZON_PROFILE_ID:
        raise HTTPException(status_code=500, detail="AMAZON_PROFILE_ID is not set")

    return {
        "Authorization": f"Bearer {get_access_token()}",
        "Amazon-Advertising-API-ClientId": AMAZON_CLIENT_ID,
        "Amazon-Advertising-API-Scope": AMAZON_PROFILE_ID,
    }


def extract_duplicate_report_id(text: str):
    match = re.search(
        r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
        text,
    )
    return match.group(0) if match else None


def money(value):
    try:
        return round(float(value or 0), 2)
    except Exception:
        return 0.0


def integer(value):
    try:
        return int(value or 0)
    except Exception:
        return 0


@app.get("/")
def root():
    return {"status": "ok", "message": "Amazon Ads ChatGPT API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/oauth/callback")
def oauth_callback(code: str = None, state: str = None):
    return {
        "message": "Authorization code received. Copy the code value and exchange it for a refresh token.",
        "code": code,
        "state": state,
    }


@app.get("/profiles")
def get_profiles(x_api_key: str = Header(...)):
    verify_key(x_api_key)

    headers = {
        "Authorization": f"Bearer {get_access_token()}",
        "Amazon-Advertising-API-ClientId": AMAZON_CLIENT_ID,
    }

    r = requests.get(f"{ADS_BASE_URL}/v2/profiles", headers=headers, timeout=30)

    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return r.json()


@app.get("/sponsored-products/campaigns")
def get_sp_campaigns(x_api_key: str = Header(...)):
    verify_key(x_api_key)

    headers = ads_headers()
    headers["Accept"] = "application/vnd.spCampaign.v3+json"
    headers["Content-Type"] = "application/vnd.spCampaign.v3+json"

    r = requests.post(
        f"{ADS_BASE_URL}/sp/campaigns/list",
        headers=headers,
        json={"maxResults": 100, "includeExtendedDataFields": True},
        timeout=30,
    )

    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return r.json()


def create_report(report_type: str):
    headers = ads_headers()
    headers["Accept"] = "application/vnd.createasyncreportrequest.v3+json"
    headers["Content-Type"] = "application/vnd.createasyncreportrequest.v3+json"

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=29)

    timestamp = int(time.time())

    if report_type == "campaigns":
        body = {
            "name": f"SP Campaign Performance {timestamp}",
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "configuration": {
                "adProduct": "SPONSORED_PRODUCTS",
                "groupBy": ["campaign"],
                "columns": [
                    "campaignId",
                    "campaignName",
                    "campaignStatus",
                    "impressions",
                    "clicks",
                    "cost",
                    "sales7d",
                    "purchases7d",
                    "unitsSoldClicks7d",
                ],
                "reportTypeId": "spCampaigns",
                "timeUnit": "SUMMARY",
                "format": "GZIP_JSON",
            },
        }

    elif report_type == "search_terms":
        body = {
            "name": f"SP Search Term Performance {timestamp}",
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "configuration": {
                "adProduct": "SPONSORED_PRODUCTS",
                "groupBy": ["searchTerm"],
                "columns": [
                    "campaignId",
                    "campaignName",
                    "adGroupId",
                    "adGroupName",
                    "keywordId",
                    "keyword",
                    "matchType",
                    "searchTerm",
                    "impressions",
                    "clicks",
                    "cost",
                    "sales7d",
                    "purchases7d",
                    "unitsSoldClicks7d",
                ],
                "reportTypeId": "spSearchTerm",
                "timeUnit": "SUMMARY",
                "format": "GZIP_JSON",
            },
        }

    else:
        raise HTTPException(status_code=400, detail="Invalid report type")

    r = requests.post(
        f"{ADS_BASE_URL}/reporting/reports",
        headers=headers,
        json=body,
        timeout=30,
    )

    if not r.ok:
        duplicate_id = extract_duplicate_report_id(r.text)
        if duplicate_id:
            return {"reportId": duplicate_id, "status": "DUPLICATE_REUSED"}
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return r.json()


@app.post("/reports/sp-campaigns")
def create_sp_campaign_report(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return create_report("campaigns")


@app.post("/reports/sp-search-terms")
def create_sp_search_terms_report(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return create_report("search_terms")
@app.get("/reports/analyze/{campaign_report_id}/{search_term_report_id}")
def analyze_completed_reports(
    campaign_report_id: str,
    search_term_report_id: str,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)

    campaign_download = download_report_data(campaign_report_id)
    search_download = download_report_data(search_term_report_id)

    if not campaign_download.get("ready") or not search_download.get("ready"):
        return {
            "status": "PENDING",
            "message": "One or both reports are not ready yet. Try again shortly.",
            "campaignReport": {
                "id": campaign_report_id,
                "status": campaign_download.get("status"),
            },
            "searchTermReport": {
                "id": search_term_report_id,
                "status": search_download.get("status"),
            },
        }

    campaigns = enrich_rows(campaign_download.get("data", []))
    search_terms = enrich_rows(search_download.get("data", []))

    return {
        "status": "COMPLETED",
        "campaignReportId": campaign_report_id,
        "searchTermReportId": search_term_report_id,
        "summary": {
            "campaigns": summarize(campaigns),
            "searchTerms": summarize(search_terms),
        },
        "alerts": {
            "highSpendNoSalesCampaigns": sorted(
                [r for r in campaigns if r["spend"] >= 5 and r["sales"] == 0],
                key=lambda r: r["spend"],
                reverse=True,
            )[:10],
            "highAcosCampaigns": sorted(
                [r for r in campaigns if r["acos"] is not None and r["acos"] >= 40],
                key=lambda r: r["acos"],
                reverse=True,
            )[:10],
            "wastedSearchTerms": sorted(
                [r for r in search_terms if r["spend"] >= 3 and r["sales"] == 0],
                key=lambda r: r["spend"],
                reverse=True,
            )[:25],
        },
        "opportunities": {
            "bestCampaigns": sorted(
                [r for r in campaigns if r["sales"] > 0],
                key=lambda r: r["sales"],
                reverse=True,
            )[:10],
            "strongSearchTerms": sorted(
                [r for r in search_terms if r["sales"] > 0 and r["roas"] is not None],
                key=lambda r: r["roas"],
                reverse=True,
            )[:25],
        },
    }


@app.post("/reports/analyze")
def analyze_ads_account(x_api_key: str = Header(...)):
    verify_key(x_api_key)

    now = time.time()

    campaign_id = LATEST_ANALYSIS.get("campaignReportId")
    search_id = LATEST_ANALYSIS.get("searchTermReportId")
    created_at = LATEST_ANALYSIS.get("createdAt")

    reuse_existing = (
        campaign_id
        and search_id
        and created_at
        and now - created_at < 900
    )

    if not reuse_existing:
        campaign_report = create_report("campaigns")
        search_report = create_report("search_terms")

        campaign_id = campaign_report.get("reportId")
        search_id = search_report.get("reportId")

        LATEST_ANALYSIS["campaignReportId"] = campaign_id
        LATEST_ANALYSIS["searchTermReportId"] = search_id
        LATEST_ANALYSIS["createdAt"] = now

    campaign_download = download_report_data(campaign_id)
    search_download = download_report_data(search_id)

    if not campaign_download.get("ready") or not search_download.get("ready"):
        return {
            "status": "PENDING",
            "message": "Reports are still processing. Ask again in 1-3 minutes: Analyze my Amazon Ads account.",
            "campaignReportId": campaign_id,
            "searchTermReportId": search_id,
            "campaignStatus": campaign_download.get("status"),
            "searchTermStatus": search_download.get("status"),
        }

    campaigns = enrich_rows(campaign_download.get("data", []))
    search_terms = enrich_rows(search_download.get("data", []))

    high_spend_no_sales = sorted(
        [r for r in campaigns if r["spend"] >= 5 and r["sales"] == 0],
        key=lambda r: r["spend"],
        reverse=True,
    )[:10]

    high_acos = sorted(
        [r for r in campaigns if r["acos"] is not None and r["acos"] >= 40],
        key=lambda r: r["acos"],
        reverse=True,
    )[:10]

    best_campaigns = sorted(
        [r for r in campaigns if r["sales"] > 0],
        key=lambda r: r["sales"],
        reverse=True,
    )[:10]

    wasted_search_terms = sorted(
        [r for r in search_terms if r["spend"] >= 3 and r["sales"] == 0],
        key=lambda r: r["spend"],
        reverse=True,
    )[:25]

    strong_search_terms = sorted(
        [r for r in search_terms if r["sales"] > 0 and r["roas"] is not None],
        key=lambda r: r["roas"],
        reverse=True,
    )[:25]

    return {
        "status": "COMPLETED",
        "campaignReportId": campaign_id,
        "searchTermReportId": search_id,
        "summary": {
            "campaigns": summarize(campaigns),
            "searchTerms": summarize(search_terms),
        },
        "alerts": {
            "highSpendNoSalesCampaigns": high_spend_no_sales,
            "highAcosCampaigns": high_acos,
            "wastedSearchTerms": wasted_search_terms,
        },
        "opportunities": {
            "bestCampaigns": best_campaigns,
            "strongSearchTerms": strong_search_terms,
        },
        "recommendations": [
            "Reduce bids or pause campaigns with spend and no sales.",
            "Lower bids on campaigns above target ACOS.",
            "Harvest strong converting search terms into exact-match campaigns.",
            "Add irrelevant high-spend/no-sale search terms as negatives.",
            "Increase budget on profitable campaigns that are limited by budget.",
        ],
    }
@app.get("/reports/{report_id}")
def get_report_status(report_id: str, x_api_key: str = Header(...)):
    verify_key(x_api_key)

    headers = ads_headers()
    headers["Accept"] = "application/vnd.getasyncreportresponse.v3+json"

    r = requests.get(
        f"{ADS_BASE_URL}/reporting/reports/{report_id}",
        headers=headers,
        timeout=30,
    )

    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return r.json()


def download_report_data(report_id: str):
    headers = ads_headers()
    headers["Accept"] = "application/vnd.getasyncreportresponse.v3+json"

    status_response = requests.get(
        f"{ADS_BASE_URL}/reporting/reports/{report_id}",
        headers=headers,
        timeout=30,
    )

    if not status_response.ok:
        raise HTTPException(
            status_code=status_response.status_code,
            detail=status_response.text,
        )

    report_info = status_response.json()

    if report_info.get("status") != "COMPLETED":
        return {
            "status": report_info.get("status"),
            "ready": False,
            "report": report_info,
            "data": [],
        }

    report_url = report_info.get("url")

    if not report_url:
        raise HTTPException(status_code=500, detail="Report completed but no download URL found")

    file_response = requests.get(report_url, timeout=60)

    if not file_response.ok:
        raise HTTPException(
            status_code=file_response.status_code,
            detail=file_response.text,
        )

    try:
        decompressed = gzip.decompress(file_response.content)
        data = json.loads(decompressed.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse report: {str(e)}")

    return {
        "status": "COMPLETED",
        "ready": True,
        "rows": len(data) if isinstance(data, list) else None,
        "data": data,
    }


@app.get("/reports/{report_id}/download")
def download_report(report_id: str, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return download_report_data(report_id)


def enrich_rows(rows):
    enriched = []

    for row in rows:
        spend = money(row.get("cost"))
        sales = money(row.get("sales7d"))
        clicks = integer(row.get("clicks"))
        impressions = integer(row.get("impressions"))
        orders = integer(row.get("purchases7d"))

        row["spend"] = spend
        row["sales"] = sales
        row["orders"] = orders
        row["acos"] = round((spend / sales * 100), 2) if sales > 0 else None
        row["roas"] = round((sales / spend), 2) if spend > 0 else None
        row["ctr"] = round((clicks / impressions * 100), 2) if impressions > 0 else None
        row["cpc"] = round((spend / clicks), 2) if clicks > 0 else None
        row["conversionRate"] = round((orders / clicks * 100), 2) if clicks > 0 else None

        enriched.append(row)

    return enriched


def summarize(rows):
    total_spend = sum(money(r.get("cost")) for r in rows)
    total_sales = sum(money(r.get("sales7d")) for r in rows)
    total_clicks = sum(integer(r.get("clicks")) for r in rows)
    total_impressions = sum(integer(r.get("impressions")) for r in rows)
    total_orders = sum(integer(r.get("purchases7d")) for r in rows)

    return {
        "spend": round(total_spend, 2),
        "sales": round(total_sales, 2),
        "acos": round(total_spend / total_sales * 100, 2) if total_sales > 0 else None,
        "roas": round(total_sales / total_spend, 2) if total_spend > 0 else None,
        "impressions": total_impressions,
        "clicks": total_clicks,
        "ctr": round(total_clicks / total_impressions * 100, 2) if total_impressions > 0 else None,
        "cpc": round(total_spend / total_clicks, 2) if total_clicks > 0 else None,
        "orders": total_orders,
        "conversionRate": round(total_orders / total_clicks * 100, 2) if total_clicks > 0 else None,
    }


@app.get("/reports/analyze/{campaign_report_id}/{search_term_report_id}")
def analyze_completed_reports(
    campaign_report_id: str,
    search_term_report_id: str,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)

    campaign_download = download_report_data(campaign_report_id)
    search_download = download_report_data(search_term_report_id)

    if not campaign_download.get("ready") or not search_download.get("ready"):
        return {
            "status": "PENDING",
            "message": "One or both reports are not ready yet. Try again shortly.",
            "campaignReport": {
                "id": campaign_report_id,
                "status": campaign_download.get("status"),
            },
            "searchTermReport": {
                "id": search_term_report_id,
                "status": search_download.get("status"),
            },
        }

    campaigns = enrich_rows(campaign_download.get("data", []))
    search_terms = enrich_rows(search_download.get("data", []))

    campaign_summary = summarize(campaigns)
    search_term_summary = summarize(search_terms)

    high_spend_no_sales_campaigns = sorted(
        [r for r in campaigns if r["spend"] >= 5 and r["sales"] == 0],
        key=lambda r: r["spend"],
        reverse=True,
    )[:10]

    high_acos_campaigns = sorted(
        [r for r in campaigns if r["acos"] is not None and r["acos"] >= 40],
        key=lambda r: r["acos"],
        reverse=True,
    )[:10]

    best_campaigns = sorted(
        [r for r in campaigns if r["sales"] > 0],
        key=lambda r: r["sales"],
        reverse=True,
    )[:10]

    wasted_search_terms = sorted(
        [r for r in search_terms if r["spend"] >= 3 and r["sales"] == 0],
        key=lambda r: r["spend"],
        reverse=True,
    )[:25]

    strong_search_terms = sorted(
        [r for r in search_terms if r["sales"] > 0 and r["roas"] is not None],
        key=lambda r: r["roas"],
        reverse=True,
    )[:25]

    low_ctr_campaigns = sorted(
        [r for r in campaigns if r["impressions"] >= 500 and r["ctr"] is not None and r["ctr"] < 0.25],
        key=lambda r: r["ctr"],
    )[:10]

    recommendations = []

    for r in high_spend_no_sales_campaigns[:5]:
        recommendations.append({
            "priority": "High",
            "type": "Reduce waste",
            "campaign": r.get("campaignName"),
            "recommendation": "Lower bids, reduce budget, or inspect targeting because this campaign spent with no attributed sales.",
            "spend": r["spend"],
            "sales": r["sales"],
        })

    for r in high_acos_campaigns[:5]:
        recommendations.append({
            "priority": "High",
            "type": "Improve profitability",
            "campaign": r.get("campaignName"),
            "recommendation": "Reduce bids or tighten targeting because ACOS is above 40%.",
            "acos": r["acos"],
            "spend": r["spend"],
            "sales": r["sales"],
        })

    for r in best_campaigns[:5]:
        recommendations.append({
            "priority": "Medium",
            "type": "Scale winner",
            "campaign": r.get("campaignName"),
            "recommendation": "Consider increasing budget if this campaign is limited or consistently profitable.",
            "acos": r["acos"],
            "roas": r["roas"],
            "sales": r["sales"],
        })

    for r in wasted_search_terms[:10]:
        recommendations.append({
            "priority": "High",
            "type": "Negative keyword candidate",
            "campaign": r.get("campaignName"),
            "searchTerm": r.get("searchTerm"),
            "recommendation": "Consider adding this search term as a negative if it is irrelevant or repeatedly spends without sales.",
            "spend": r["spend"],
            "clicks": r.get("clicks"),
        })

    return {
        "status": "COMPLETED",
        "campaignReportId": campaign_report_id,
        "searchTermReportId": search_term_report_id,
        "summary": {
            "campaigns": campaign_summary,
            "searchTerms": search_term_summary,
        },
        "alerts": {
            "highSpendNoSalesCampaigns": high_spend_no_sales_campaigns,
            "highAcosCampaigns": high_acos_campaigns,
            "lowCtrCampaigns": low_ctr_campaigns,
            "wastedSearchTerms": wasted_search_terms,
        },
        "opportunities": {
            "bestCampaigns": best_campaigns,
            "strongSearchTerms": strong_search_terms,
        },
        "recommendations": recommendations,
        "raw": {
            "campaigns": campaigns,
            "searchTerms": search_terms,
        },
    }
@app.get("/dashboard")
def get_dashboard(x_api_key: str = Header(...)):
    verify_key(x_api_key)

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
@app.post("/dashboard/collect/{campaign_report_id}/{search_term_report_id}")
def collect_dashboard(
    campaign_report_id: str,
    search_term_report_id: str,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)

    campaign_download = download_report_data(campaign_report_id)
    search_download = download_report_data(search_term_report_id)

    if not campaign_download.get("ready") or not search_download.get("ready"):
        return {
            "status": "PENDING",
            "message": "One or both reports are not ready yet.",
            "campaignStatus": campaign_download.get("status"),
            "searchTermStatus": search_download.get("status"),
        }

    campaigns = enrich_rows(campaign_download.get("data", []))
    search_terms = enrich_rows(search_download.get("data", []))

    summary = summarize(campaigns)

    alerts = {
        "highSpendNoSalesCampaigns": sorted(
            [r for r in campaigns if r["spend"] >= 5 and r["sales"] == 0],
            key=lambda r: r["spend"],
            reverse=True,
        )[:10],
        "highAcosCampaigns": sorted(
            [r for r in campaigns if r["acos"] is not None and r["acos"] >= 40],
            key=lambda r: r["acos"],
            reverse=True,
        )[:10],
        "wastedSearchTerms": sorted(
            [r for r in search_terms if r["spend"] >= 3 and r["sales"] == 0],
            key=lambda r: r["spend"],
            reverse=True,
        )[:25],
    }

    recommendations = [
        {
            "priority": "High",
            "type": "Waste reduction",
            "recommendation": "Review campaigns and search terms with spend but no sales.",
        },
        {
            "priority": "High",
            "type": "ACOS control",
            "recommendation": "Reduce bids on campaigns above target ACOS.",
        },
        {
            "priority": "Medium",
            "type": "Keyword harvesting",
            "recommendation": "Move strong converting search terms into exact-match campaigns.",
        },
    ]

    health_score = 100
    if summary.get("acos") and summary["acos"] > 40:
        health_score -= 25
    if len(alerts["highSpendNoSalesCampaigns"]) > 0:
        health_score -= 15
    if len(alerts["wastedSearchTerms"]) > 5:
        health_score -= 15

    health_score = max(0, health_score)

    db = SessionLocal()

    today = date.today()

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
        existing.health_score = health_score
        existing.alerts = alerts
        existing.recommendations = recommendations
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
            health_score=health_score,
            alerts=alerts,
            recommendations=recommendations,
        )
        db.add(dashboard)

    db.commit()
    db.close()

    return {
        "status": "OK",
        "message": "Dashboard collected and saved.",
        "summary": summary,
        "health_score": health_score,
        "alerts": alerts,
        "recommendations": recommendations,
    }
def scheduled_amazon_ads_collection():
    try:
        print("Starting scheduled Amazon Ads collection...")

        campaign_report = create_report("campaigns")
        search_report = create_report("search_terms")

        campaign_id = campaign_report.get("reportId")
        search_id = search_report.get("reportId")

        db = SessionLocal()

        job = ScheduledReportJob(
            date=date.today(),
            campaign_report_id=campaign_id,
            search_term_report_id=search_id,
            status="PENDING",
        )

        db.add(job)
        db.commit()
        db.close()

        print("Scheduled reports created:", campaign_id, search_id)

    except Exception as e:
        print("Scheduled collection failed:", str(e))

scheduler = BackgroundScheduler(timezone="America/Regina")

scheduler = BackgroundScheduler(timezone="America/Regina")

scheduler.add_job(
    scheduled_amazon_ads_collection,
    "cron",
    hour=6,
    minute=0,
    id="daily_amazon_ads_collection",
    replace_existing=True,
)

scheduler.start()
