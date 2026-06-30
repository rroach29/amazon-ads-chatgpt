"""
Business OS v3.4.2
Amazon Ads Execution Adapter

This is the only module in v3.4.2 that mutates Amazon Ads.

Supported live actions:
- PAUSE_CAMPAIGN
- RESUME_CAMPAIGN
- SET_BUDGET
- INCREASE_BUDGET
- DECREASE_BUDGET

Safety:
- Live execution requires dry_run=False AND confirm_live=True.
- Dry-run remains the default.
- Campaign ID is required for all supported actions.
- Budget actions require a resolved budget amount.
"""

import requests
from fastapi import HTTPException

from amazon_ads import ADS_BASE_URL, ads_headers


SP_CAMPAIGN_CONTENT_TYPE = "application/vnd.spCampaign.v3+json"


def _get_payload_value(payload, *keys, default=None):
    if not isinstance(payload, dict):
        return default

    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value

    return default


def _get_campaign_id(payload):
    value = _get_payload_value(payload, "campaign_id", "campaignId")
    return str(value) if value is not None else None


def _to_float(value):
    if value is None:
        return None

    try:
        return float(value)
    except Exception:
        return None


def _build_headers(profile_id=None, country_code=None):
    headers = ads_headers(profile_id=profile_id, country_code=country_code)
    headers["Accept"] = SP_CAMPAIGN_CONTENT_TYPE
    headers["Content-Type"] = SP_CAMPAIGN_CONTENT_TYPE
    return headers


def _dry_run_result(action, profile_id, country_code, campaign_id, update_payload):
    return {
        "success": True,
        "dry_run": True,
        "http_status": None,
        "amazon_request_id": None,
        "action": action,
        "profile_id": profile_id,
        "country_code": country_code,
        "campaign_id": campaign_id,
        "request_payload": update_payload,
        "response_json": {
            "mode": "dry_run",
            "message": "No Amazon Ads changes were made.",
            "action": action,
            "campaign_id": campaign_id,
            "request_payload": update_payload,
        },
    }


def _send_campaign_update(profile_id, country_code, update_payload):
    """
    Sponsored Products v3 campaign update.

    Amazon Ads Sponsored Products campaign management v3 uses the SP campaign
    media type and a batch campaign update endpoint.

    If Amazon returns a validation error, Business OS stores the exact response
    in ExecutionResult for troubleshooting.
    """
    headers = _build_headers(profile_id=profile_id, country_code=country_code)

    response = requests.put(
        f"{ADS_BASE_URL}/sp/campaigns",
        headers=headers,
        json={"campaigns": [update_payload]},
        timeout=30,
    )

    amazon_request_id = response.headers.get("x-amzn-requestid") or response.headers.get("x-amz-request-id")

    try:
        response_json = response.json()
    except Exception:
        response_json = {"raw": response.text}

    if not response.ok:
        return {
            "success": False,
            "dry_run": False,
            "http_status": response.status_code,
            "amazon_request_id": amazon_request_id,
            "response_json": response_json,
            "error_message": response.text,
        }

    return {
        "success": True,
        "dry_run": False,
        "http_status": response.status_code,
        "amazon_request_id": amazon_request_id,
        "response_json": response_json,
        "error_message": None,
    }


def pause_campaign(profile_id, country_code, payload, dry_run=True):
    campaign_id = _get_campaign_id(payload)

    update_payload = {
        "campaignId": campaign_id,
        "state": "PAUSED",
    }

    if dry_run:
        return _dry_run_result("PAUSE_CAMPAIGN", profile_id, country_code, campaign_id, update_payload)

    result = _send_campaign_update(profile_id, country_code, update_payload)
    result.update({
        "action": "PAUSE_CAMPAIGN",
        "campaign_id": campaign_id,
        "request_payload": update_payload,
    })
    return result


def resume_campaign(profile_id, country_code, payload, dry_run=True):
    campaign_id = _get_campaign_id(payload)

    update_payload = {
        "campaignId": campaign_id,
        "state": "ENABLED",
    }

    if dry_run:
        return _dry_run_result("RESUME_CAMPAIGN", profile_id, country_code, campaign_id, update_payload)

    result = _send_campaign_update(profile_id, country_code, update_payload)
    result.update({
        "action": "RESUME_CAMPAIGN",
        "campaign_id": campaign_id,
        "request_payload": update_payload,
    })
    return result


def _resolve_budget(payload, mode):
    explicit_budget = _to_float(
        _get_payload_value(
            payload,
            "new_budget",
            "newBudget",
            "budget",
            "daily_budget",
            "dailyBudget",
            "recommended_budget",
            "recommendedBudget",
        )
    )

    current_budget = _to_float(
        _get_payload_value(
            payload,
            "current_budget",
            "currentBudget",
            "existing_budget",
            "existingBudget",
        )
    )

    percent = _to_float(
        _get_payload_value(
            payload,
            "percent",
            "percentage",
            "increase_percent",
            "decrease_percent",
            "change_percent",
        )
    )

    amount = _to_float(
        _get_payload_value(
            payload,
            "amount",
            "change_amount",
            "increase_amount",
            "decrease_amount",
        )
    )

    if mode == "SET_BUDGET":
        return explicit_budget

    if current_budget is None:
        # Some decision payloads may provide only a recommended final budget.
        return explicit_budget

    if percent is not None:
        if mode == "INCREASE_BUDGET":
            return round(current_budget * (1 + percent / 100), 2)
        if mode == "DECREASE_BUDGET":
            return round(current_budget * (1 - percent / 100), 2)

    if amount is not None:
        if mode == "INCREASE_BUDGET":
            return round(current_budget + amount, 2)
        if mode == "DECREASE_BUDGET":
            return round(current_budget - amount, 2)

    return explicit_budget


def set_budget(profile_id, country_code, payload, dry_run=True, action="SET_BUDGET"):
    campaign_id = _get_campaign_id(payload)
    budget = _resolve_budget(payload, action)

    update_payload = {
        "campaignId": campaign_id,
        "budget": {
            "budgetType": "DAILY",
            "budget": budget,
        },
    }

    if dry_run:
        return _dry_run_result(action, profile_id, country_code, campaign_id, update_payload)

    result = _send_campaign_update(profile_id, country_code, update_payload)
    result.update({
        "action": action,
        "campaign_id": campaign_id,
        "request_payload": update_payload,
    })
    return result


def execute_amazon_action(action, profile_id, country_code, payload, dry_run=True):
    if action == "PAUSE_CAMPAIGN":
        return pause_campaign(profile_id, country_code, payload, dry_run=dry_run)

    if action == "RESUME_CAMPAIGN":
        return resume_campaign(profile_id, country_code, payload, dry_run=dry_run)

    if action == "SET_BUDGET":
        return set_budget(profile_id, country_code, payload, dry_run=dry_run, action="SET_BUDGET")

    if action == "INCREASE_BUDGET":
        return set_budget(profile_id, country_code, payload, dry_run=dry_run, action="INCREASE_BUDGET")

    if action == "DECREASE_BUDGET":
        return set_budget(profile_id, country_code, payload, dry_run=dry_run, action="DECREASE_BUDGET")

    raise HTTPException(
        status_code=400,
        detail=f"Unsupported Amazon live execution action: {action}",
    )
