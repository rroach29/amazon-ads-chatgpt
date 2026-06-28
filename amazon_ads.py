import os
import json
import gzip
import re
import time
from datetime import date, timedelta

import requests
from fastapi import HTTPException

AMAZON_CLIENT_ID = os.getenv("AMAZON_CLIENT_ID")
AMAZON_CLIENT_SECRET = os.getenv("AMAZON_CLIENT_SECRET")
AMAZON_REFRESH_TOKEN = os.getenv("AMAZON_REFRESH_TOKEN")
AMAZON_PROFILE_ID = os.getenv("AMAZON_PROFILE_ID")

TOKEN_URL = "https://api.amazon.com/auth/o2/token"
ADS_BASE_URL = "https://advertising-api.amazon.com"


def get_access_token():
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
    return {
        "Authorization": f"Bearer {get_access_token()}",
        "Amazon-Advertising-API-ClientId": AMAZON_CLIENT_ID,
        "Amazon-Advertising-API-Scope": AMAZON_PROFILE_ID,
    }


def create_report(report_type: str):
    headers = ads_headers()
    headers["Accept"] = "application/vnd.createasyncreportrequest.v3+json"
    headers["Content-Type"] = "application/vnd.createasyncreportrequest.v3+json"

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=29)
    timestamp = int(time.time())

    if report_type == "campaigns":
        config = {
            "name": f"SP Campaign Performance {timestamp}",
            "reportTypeId": "spCampaigns",
            "groupBy": ["campaign"],
            "columns": [
                "campaignId", "campaignName", "campaignStatus",
                "impressions", "clicks", "cost",
                "sales7d", "purchases7d", "unitsSoldClicks7d",
            ],
        }
    elif report_type == "search_terms":
        config = {
            "name": f"SP Search Term Performance {timestamp}",
            "reportTypeId": "spSearchTerm",
            "groupBy": ["searchTerm"],
            "columns": [
                "campaignId", "campaignName", "adGroupId", "adGroupName",
                "keywordId", "keyword", "matchType", "searchTerm",
                "impressions", "clicks", "cost",
                "sales7d", "purchases7d", "unitsSoldClicks7d",
            ],
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid report type")

    body = {
        "name": config["name"],
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "configuration": {
            "adProduct": "SPONSORED_PRODUCTS",
            "groupBy": config["groupBy"],
            "columns": config["columns"],
            "reportTypeId": config["reportTypeId"],
            "timeUnit": "SUMMARY",
            "format": "GZIP_JSON",
        },
    }

    response = requests.post(
        f"{ADS_BASE_URL}/reporting/reports",
        headers=headers,
        json=body,
        timeout=30,
    )

    if not response.ok:
        match = re.search(
            r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
            response.text,
        )
        if match:
            return {"reportId": match.group(0), "status": "DUPLICATE_REUSED"}

        raise HTTPException(status_code=response.status_code, detail=response.text)

    return response.json()


def get_report_status(report_id: str):
    headers = ads_headers()
    headers["Accept"] = "application/vnd.getasyncreportresponse.v3+json"

    response = requests.get(
        f"{ADS_BASE_URL}/reporting/reports/{report_id}",
        headers=headers,
        timeout=30,
    )

    if not response.ok:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    return response.json()


def download_report_data(report_id: str):
    report_info = get_report_status(report_id)

    if report_info.get("status") != "COMPLETED":
        return {
            "ready": False,
            "status": report_info.get("status"),
            "data": [],
            "report": report_info,
        }

    report_url = report_info.get("url")

    if not report_url:
        raise HTTPException(status_code=500, detail="Report completed but no URL found")

    file_response = requests.get(report_url, timeout=60)

    if not file_response.ok:
        raise HTTPException(status_code=file_response.status_code, detail=file_response.text)

    data = json.loads(gzip.decompress(file_response.content).decode("utf-8"))

    return {
        "ready": True,
        "status": "COMPLETED",
        "rows": len(data) if isinstance(data, list) else None,
        "data": data,
    }
