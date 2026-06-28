import os
import json
import gzip
import time
import re

from datetime import date, timedelta

import requests
from fastapi import FastAPI, Header, HTTPException


app = FastAPI(title="Amazon Ads ChatGPT API")

AMAZON_CLIENT_ID = os.getenv("AMAZON_CLIENT_ID")
AMAZON_CLIENT_SECRET = os.getenv("AMAZON_CLIENT_SECRET")
AMAZON_REFRESH_TOKEN = os.getenv("AMAZON_REFRESH_TOKEN")
AMAZON_PROFILE_ID = os.getenv("AMAZON_PROFILE_ID")
CHATGPT_API_KEY = os.getenv("CHATGPT_API_KEY")

TOKEN_URL = "https://api.amazon.com/auth/o2/token"
ADS_BASE_URL = "https://advertising-api.amazon.com"


def verify_key(x_api_key: str):
    if not CHATGPT_API_KEY:
        raise HTTPException(status_code=500, detail="CHATGPT_API_KEY is not set")

    if x_api_key != CHATGPT_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


def get_access_token():
    missing = []

    if not AMAZON_CLIENT_ID:
        missing.append("AMAZON_CLIENT_ID")
    if not AMAZON_CLIENT_SECRET:
        missing.append("AMAZON_CLIENT_SECRET")
    if not AMAZON_REFRESH_TOKEN:
        missing.append("AMAZON_REFRESH_TOKEN")

    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"Missing environment variables: {', '.join(missing)}",
        )

    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": AMAZON_REFRESH_TOKEN,
            "client_id": AMAZON_CLIENT_ID,
            "client_secret": AMAZON_CLIENT_SECRET,
        },
        timeout=30,
    )

    if not response.ok:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    return response.json()["access_token"]


def ads_headers():
    if not AMAZON_PROFILE_ID:
        raise HTTPException(status_code=500, detail="AMAZON_PROFILE_ID is not set")

    token = get_access_token()

    return {
        "Authorization": f"Bearer {token}",
        "Amazon-Advertising-API-ClientId": AMAZON_CLIENT_ID,
        "Amazon-Advertising-API-Scope": AMAZON_PROFILE_ID,
    }


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "Amazon Ads ChatGPT API is running",
    }


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

    token = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Amazon-Advertising-API-ClientId": AMAZON_CLIENT_ID,
    }

    r = requests.get(
        f"{ADS_BASE_URL}/v2/profiles",
        headers=headers,
        timeout=30,
    )

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
        json={
            "maxResults": 100,
            "includeExtendedDataFields": True,
        },
        timeout=30,
    )

    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return r.json()


@app.post("/reports/sp-campaigns")
def create_sp_campaign_report(x_api_key: str = Header(...)):
    verify_key(x_api_key)

    headers = ads_headers()
    headers["Accept"] = "application/vnd.createasyncreportrequest.v3+json"
    headers["Content-Type"] = "application/vnd.createasyncreportrequest.v3+json"

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=29)

    body = {
        "name": "SP Campaign Performance - Last 30 Days",
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

    r = requests.post(
        f"{ADS_BASE_URL}/reporting/reports",
        headers=headers,
        json=body,
        timeout=30,
    )

    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return r.json()


@app.post("/reports/sp-search-terms")
def create_sp_search_terms_report(x_api_key: str = Header(...)):
    verify_key(x_api_key)

    headers = ads_headers()
    headers["Accept"] = "application/vnd.createasyncreportrequest.v3+json"
    headers["Content-Type"] = "application/vnd.createasyncreportrequest.v3+json"

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=29)

    body = {
        "name": "SP Search Term Performance - Last 30 Days",
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

    r = requests.post(
        f"{ADS_BASE_URL}/reporting/reports",
        headers=headers,
        json=body,
        timeout=30,
    )

    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return r.json()


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


@app.get("/reports/{report_id}/download")
def download_report(report_id: str, x_api_key: str = Header(...)):
    verify_key(x_api_key)

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
            "message": "Report is not ready yet.",
            "report": report_info,
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
        "rows": len(data) if isinstance(data, list) else None,
        "data": data,
    }
@app.post("/reports/daily-analysis")
def create_daily_analysis_reports(x_api_key: str = Header(...)):
    verify_key(x_api_key)

    campaign_report = create_sp_campaign_report(x_api_key)
    search_terms_report = create_sp_search_terms_report(x_api_key)

    return {
        "message": "Daily analysis reports created",
        "campaign_report": campaign_report,
        "search_terms_report": search_terms_report,
        "next_step": "Wait 1-3 minutes, then check each report ID and download when COMPLETED.",
    }
@app.post("/reports/analyze")
def analyze_ads_account(x_api_key: str = Header(...)):
    verify_key(x_api_key)

    # Create campaign report
    try:
        campaign_report = create_sp_campaign_report(x_api_key)
        report_id = campaign_report.get("reportId")
    except HTTPException as e:
        # Amazon returns duplicate report errors with existing report ID
        match = re.search(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", str(e.detail))
        if match:
            report_id = match.group(0)
        else:
            raise e

    if not report_id:
        raise HTTPException(status_code=500, detail="No reportId found")

    # Poll report status
    report_info = None
    for _ in range(12):  # up to about 2 minutes
        report_info = get_report_status(report_id, x_api_key)

        if report_info.get("status") == "COMPLETED":
            break

        if report_info.get("status") in ["FAILED", "CANCELLED"]:
            raise HTTPException(status_code=500, detail=report_info)

        time.sleep(10)

    if not report_info or report_info.get("status") != "COMPLETED":
        return {
            "status": "PENDING",
            "reportId": report_id,
            "message": "Report is not ready yet. Try again shortly.",
            "report": report_info,
        }

    # Download parsed report
    downloaded = download_report(report_id, x_api_key)
    data = downloaded.get("data", [])

    # Summarize
    total_spend = sum(float(row.get("cost", 0) or 0) for row in data)
    total_sales = sum(float(row.get("sales7d", 0) or 0) for row in data)
    total_clicks = sum(int(row.get("clicks", 0) or 0) for row in data)
    total_impressions = sum(int(row.get("impressions", 0) or 0) for row in data)
    total_orders = sum(int(row.get("purchases7d", 0) or 0) for row in data)

    acos = (total_spend / total_sales * 100) if total_sales > 0 else None
    ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else None
    cpc = (total_spend / total_clicks) if total_clicks > 0 else None
    cvr = (total_orders / total_clicks * 100) if total_clicks > 0 else None

    enriched = []
    for row in data:
        spend = float(row.get("cost", 0) or 0)
        sales = float(row.get("sales7d", 0) or 0)
        clicks = int(row.get("clicks", 0) or 0)
        impressions = int(row.get("impressions", 0) or 0)
        orders = int(row.get("purchases7d", 0) or 0)

        row["acos"] = round((spend / sales * 100), 2) if sales > 0 else None
        row["ctr"] = round((clicks / impressions * 100), 2) if impressions > 0 else None
        row["cpc"] = round((spend / clicks), 2) if clicks > 0 else None
        row["conversionRate"] = round((orders / clicks * 100), 2) if clicks > 0 else None

        enriched.append(row)

    high_spend_no_sales = sorted(
        [r for r in enriched if float(r.get("cost", 0) or 0) > 5 and float(r.get("sales7d", 0) or 0) == 0],
        key=lambda r: float(r.get("cost", 0) or 0),
        reverse=True,
    )[:10]

    high_acos = sorted(
        [r for r in enriched if r.get("acos") is not None and r["acos"] > 40],
        key=lambda r: r["acos"],
        reverse=True,
    )[:10]

    best_converters = sorted(
        [r for r in enriched if float(r.get("sales7d", 0) or 0) > 0],
        key=lambda r: float(r.get("sales7d", 0) or 0),
        reverse=True,
    )[:10]

    return {
        "status": "COMPLETED",
        "reportId": report_id,
        "summary": {
            "spend": round(total_spend, 2),
            "sales": round(total_sales, 2),
            "acos": round(acos, 2) if acos is not None else None,
            "impressions": total_impressions,
            "clicks": total_clicks,
            "ctr": round(ctr, 2) if ctr is not None else None,
            "cpc": round(cpc, 2) if cpc is not None else None,
            "orders": total_orders,
            "conversionRate": round(cvr, 2) if cvr is not None else None,
        },
        "highSpendNoSales": high_spend_no_sales,
        "highAcosCampaigns": high_acos,
        "bestConvertingCampaigns": best_converters,
        "allCampaigns": enriched,
    }
