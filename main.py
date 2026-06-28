import os
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
        "Content-Type": "application/json",
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


@app.get("/profiles")
def get_profiles(x_api_key: str = Header(...)):
    verify_key(x_api_key)

    token = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
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
        json={
            "maxResults": 100,
            "includeExtendedDataFields": True
        },
        timeout=30,
    )

    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return r.json()


@app.get("/oauth/callback")
def oauth_callback(code: str = None, state: str = None):
    return {
        "message": "Authorization code received. Copy the code value and exchange it for a refresh token.",
        "code": code,
        "state": state,
    }
