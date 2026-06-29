import os
from typing import Any, Dict, List

import requests
from fastapi import HTTPException

from amazon.auth import get_headers


ADS_BASE_URL = os.getenv("ADS_BASE_URL", "https://advertising-api.amazon.com")


def _execution_dry_run_default() -> bool:
    """
    Safety default: live execution is OFF unless explicitly enabled.

    Set AMAZON_EXECUTION_DRY_RUN=false in Render only when you are ready
    for live Amazon Ads write actions.
    """
    value = os.getenv("AMAZON_EXECUTION_DRY_RUN", "true").strip().lower()
    return value not in {"false", "0", "no", "off"}


def _coerce_campaign_id(campaign_id: Any) -> Any:
    """
    Amazon campaign IDs are usually numeric. Keep non-numeric values as-is
    so we do not accidentally destroy a valid ID format.
    """
    if campaign_id is None:
        return None

    text = str(campaign_id).strip()

    if text.isdigit():
        return int(text)

    return text


def _sp_campaign_headers() -> Dict[str, str]:
    headers = get_headers()
    headers["Accept"] = "application/vnd.spCampaign.v3+json"
    headers["Content-Type"] = "application/vnd.spCampaign.v3+json"
    return headers


def update_sp_campaigns(
    campaign_updates: List[Dict[str, Any]],
    dry_run: bool | None = None,
) -> Dict[str, Any]:
    """
    Update Sponsored Products campaigns through Amazon Advertising API.

    This is the low-level write function. Execution handlers should call
    specific helpers such as pause_campaign() instead of calling this directly.
    """
    if dry_run is None:
        dry_run = _execution_dry_run_default()

    body = {"campaigns": campaign_updates}

    if dry_run:
        return {
            "status": "DRY_RUN",
            "action": "UPDATE_SP_CAMPAIGNS",
            "message": "Dry run only. No Amazon Ads changes were made.",
            "endpoint": "PUT /sp/campaigns",
            "body": body,
        }

    response = requests.put(
        f"{ADS_BASE_URL}/sp/campaigns",
        headers=_sp_campaign_headers(),
        json=body,
        timeout=30,
    )

    if not response.ok:
        raise HTTPException(
            status_code=response.status_code,
            detail={
                "message": "Amazon Ads campaign update failed.",
                "response": response.text,
                "body": body,
            },
        )

    try:
        amazon_response = response.json()
    except Exception:
        amazon_response = {"raw_response": response.text}

    return {
        "status": "SUCCESS",
        "action": "UPDATE_SP_CAMPAIGNS",
        "endpoint": "PUT /sp/campaigns",
        "body": body,
        "amazon_response": amazon_response,
    }


def pause_campaign(payload: Dict[str, Any], dry_run: bool | None = None) -> Dict[str, Any]:
    campaign_id = payload.get("campaign_id") or payload.get("campaignId")
    campaign_name = payload.get("campaign_name") or payload.get("campaignName")

    if not campaign_id:
        return {
            "status": "ERROR",
            "action": "PAUSE_CAMPAIGN",
            "message": "Missing campaign_id in decision payload.",
            "payload": payload,
        }

    update = {
        "campaignId": _coerce_campaign_id(campaign_id),
        "state": "PAUSED",
    }

    result = update_sp_campaigns([update], dry_run=dry_run)

    return {
        **result,
        "decision_action": "PAUSE_CAMPAIGN",
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "message": (
            f"Campaign pause {'simulated' if result.get('status') == 'DRY_RUN' else 'submitted'} "
            f"for {campaign_name or campaign_id}."
        ),
    }


def resume_campaign(payload: Dict[str, Any], dry_run: bool | None = None) -> Dict[str, Any]:
    campaign_id = payload.get("campaign_id") or payload.get("campaignId")
    campaign_name = payload.get("campaign_name") or payload.get("campaignName")

    if not campaign_id:
        return {
            "status": "ERROR",
            "action": "RESUME_CAMPAIGN",
            "message": "Missing campaign_id in payload.",
            "payload": payload,
        }

    update = {
        "campaignId": _coerce_campaign_id(campaign_id),
        "state": "ENABLED",
    }

    result = update_sp_campaigns([update], dry_run=dry_run)

    return {
        **result,
        "decision_action": "RESUME_CAMPAIGN",
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "message": (
            f"Campaign resume {'simulated' if result.get('status') == 'DRY_RUN' else 'submitted'} "
            f"for {campaign_name or campaign_id}."
        ),
    }


def update_campaign_budget(payload: Dict[str, Any], dry_run: bool | None = None) -> Dict[str, Any]:
    campaign_id = payload.get("campaign_id") or payload.get("campaignId")
    campaign_name = payload.get("campaign_name") or payload.get("campaignName")
    budget = payload.get("recommended_budget") or payload.get("daily_budget") or payload.get("budget")

    if not campaign_id:
        return {
            "status": "ERROR",
            "action": "UPDATE_CAMPAIGN_BUDGET",
            "message": "Missing campaign_id in payload.",
            "payload": payload,
        }

    if budget is None:
        return {
            "status": "ERROR",
            "action": "UPDATE_CAMPAIGN_BUDGET",
            "message": "Missing budget/recommended_budget in payload.",
            "payload": payload,
        }

    update = {
        "campaignId": _coerce_campaign_id(campaign_id),
        "budget": {
            "budgetType": "DAILY",
            "budget": float(budget),
        },
    }

    result = update_sp_campaigns([update], dry_run=dry_run)

    return {
        **result,
        "decision_action": "UPDATE_CAMPAIGN_BUDGET",
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "recommended_budget": float(budget),
        "message": (
            f"Budget update {'simulated' if result.get('status') == 'DRY_RUN' else 'submitted'} "
            f"for {campaign_name or campaign_id}."
        ),
    }
