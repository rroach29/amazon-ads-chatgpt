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


def resolve_profile(profile_id=None, country_code=None):
    """
    Resolve the Amazon Advertising profile to use.

    Priority:
    1. Explicit profile_id
    2. country_code lookup from marketplace_profiles table
    3. Existing AMAZON_PROFILE_ID fallback

    This keeps existing US behavior working while enabling CA/MX.
    """
    if profile_id:
        return {
            "profile_id": str(profile_id),
            "country_code": country_code,
            "marketplace": None,
            "currency": None,
            "source": "explicit_profile_id",
        }

    if country_code:
        try:
            from marketplace_profiles import get_marketplace_profile

            result = get_marketplace_profile(country_code=country_code)

            if result.get("status") == "OK":
                profile = result.get("profile", {})
                return {
                    "profile_id": str(profile.get("profile_id")),
                    "country_code": profile.get("country_code"),
                    "marketplace": profile.get("marketplace"),
                    "currency": profile.get("currency"),
                    "source": "marketplace_profiles",
                }

            raise HTTPException(status_code=404, detail=result.get("message"))

        except HTTPException:
            raise

        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to resolve marketplace profile for {country_code}: {exc}",
            )

    if not AMAZON_PROFILE_ID:
        raise HTTPException(
            status_code=500,
            detail="No Amazon profile configured. Set AMAZON_PROFILE_ID or provide country_code/profile_id.",
        )

    return {
        "profile_id": str(AMAZON_PROFILE_ID),
        "country_code": "US",
        "marketplace": "amazon.com",
        "currency": "USD",
        "source": "AMAZON_PROFILE_ID",
    }


def ads_headers(profile_id=None, country_code=None):
    profile = resolve_profile(profile_id=profile_id, country_code=country_code)

    return {
        "Authorization": f"Bearer {get_access_token()}",
        "Amazon-Advertising-API-ClientId": AMAZON_CLIENT_ID,
        "Amazon-Advertising-API-Scope": profile["profile_id"],
    }


def get_profiles():
    headers = {
        "Authorization": f"Bearer {get_access_token()}",
        "Amazon-Advertising-API-ClientId": AMAZON_CLIENT_ID,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    response = requests.get(
        f"{ADS_BASE_URL}/v2/profiles",
        headers=headers,
        timeout=30,
    )

    if not response.ok:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    return response.json()


def create_report(report_type: str, profile_id=None, country_code=None):
    profile = resolve_profile(profile_id=profile_id, country_code=country_code)

    headers = ads_headers(profile_id=profile["profile_id"])
    headers["Accept"] = "application/vnd.createasyncreportrequest.v3+json"
    headers["Content-Type"] = "application/vnd.createasyncreportrequest.v3+json"

    # Business OS v3.8.2 fix:
    # Dashboard, Morning Brief, and daily decisions should use ONE reporting day.
    # Previously this used a 30-day range:
    #     start_date = end_date - timedelta(days=29)
    # with timeUnit=SUMMARY, which produced inflated "daily" dashboard totals.
    #
    # Amazon reporting can still expose sales7d attribution fields, but spend/clicks
    # are now constrained to yesterday only.
    end_date = date.today() - timedelta(days=1)
    start_date = end_date

    timestamp = int(time.time())
    profile_label = profile.get("country_code") or profile.get("profile_id")

    if report_type == "campaigns":
        config = {
            "name": f"SP Daily Campaign Performance {profile_label} {end_date.isoformat()} {timestamp}",
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
            "name": f"SP Daily Search Term Performance {profile_label} {end_date.isoformat()} {timestamp}",
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
            return {
                "reportId": match.group(0),
                "status": "DUPLICATE_REUSED",
                "profile": profile,
                "date_range": {
                    "startDate": start_date.isoformat(),
                    "endDate": end_date.isoformat(),
                    "mode": "DAILY",
                },
            }

        raise HTTPException(status_code=response.status_code, detail=response.text)

    data = response.json()
    data["profile"] = profile
    data["date_range"] = {
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "mode": "DAILY",
    }
    return data


def get_report_status(report_id: str, profile_id=None, country_code=None):
    profile = resolve_profile(profile_id=profile_id, country_code=country_code)

    headers = ads_headers(profile_id=profile["profile_id"])
    headers["Accept"] = "application/vnd.getasyncreportresponse.v3+json"

    response = requests.get(
        f"{ADS_BASE_URL}/reporting/reports/{report_id}",
        headers=headers,
        timeout=30,
    )

    if not response.ok:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    data = response.json()
    data["profile"] = profile
    return data


def download_report_data(report_id: str, profile_id=None, country_code=None):
    profile = resolve_profile(profile_id=profile_id, country_code=country_code)
    report_info = get_report_status(
        report_id,
        profile_id=profile["profile_id"],
    )

    if report_info.get("status") != "COMPLETED":
        return {
            "ready": False,
            "status": report_info.get("status"),
            "data": [],
            "report": report_info,
            "profile": profile,
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
        "profile": profile,
    }
