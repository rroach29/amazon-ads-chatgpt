"""
Business OS v3.7.0
Amazon Ads Execution Adapter with Budget Management

Supported live actions:
- PAUSE_CAMPAIGN
- RESUME_CAMPAIGN
- SET_BUDGET
- INCREASE_BUDGET
- DECREASE_BUDGET

Budget improvements in v3.7.0:
- Fetches current live budget from Amazon before budget changes.
- Calculates before/after budget values.
- Enforces max % change guardrails.
- Stores before/after budget values in ExecutionResult response_json.
- Enables safe budget rollback in execution_audit.py.

Safety:
- Dry-run remains supported.
- Live execution still requires dry_run=false and confirm_live=true in execution_engine.py.
"""

import requests
from fastapi import HTTPException

from amazon_ads import ADS_BASE_URL, ads_headers


SP_CAMPAIGN_CONTENT_TYPE = "application/vnd.spCampaign.v3+json"

BUDGET_LIMITS = {
    "min_daily_budget": 1.00,
    "max_daily_budget": 500.00,
    "max_increase_percent": 50.00,
    "max_decrease_percent": 50.00,
}


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


def _round_budget(value):
    value = _to_float(value)
    if value is None:
        return None
    return round(value, 2)


def _build_headers(profile_id=None, country_code=None):
    headers = ads_headers(profile_id=profile_id, country_code=country_code)
    headers["Accept"] = SP_CAMPAIGN_CONTENT_TYPE
    headers["Content-Type"] = SP_CAMPAIGN_CONTENT_TYPE
    return headers


def _extract_amazon_request_id(response):
    return (
        response.headers.get("x-amzn-requestid")
        or response.headers.get("x-amz-request-id")
        or response.headers.get("x-amzn-RequestId")
    )


def _dry_run_result(action, profile_id, country_code, campaign_id, update_payload, extra=None):
    extra = extra or {}

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
        **extra,
        "response_json": {
            "mode": "dry_run",
            "message": "No Amazon Ads changes were made.",
            "action": action,
            "campaign_id": campaign_id,
            "request_payload": update_payload,
            **extra,
        },
    }


def get_campaign_live(profile_id, country_code, campaign_id):
    """
    Fetch live campaign details from Amazon.

    This uses Sponsored Products v3 campaign list endpoint. If Amazon changes
    response shape, the exact error/response is returned so Business OS can fail
    safely instead of guessing current budget.
    """
    headers = _build_headers(profile_id=profile_id, country_code=country_code)

    body = {
        "campaignIdFilter": {
            "include": [str(campaign_id)]
        },
        "maxResults": 10,
    }

    response = requests.post(
        f"{ADS_BASE_URL}/sp/campaigns/list",
        headers=headers,
        json=body,
        timeout=30,
    )

    amazon_request_id = _extract_amazon_request_id(response)

    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text}

    if not response.ok:
        return {
            "success": False,
            "http_status": response.status_code,
            "amazon_request_id": amazon_request_id,
            "response_json": data,
            "error_message": response.text,
        }

    campaigns = data.get("campaigns")
    if not isinstance(campaigns, list):
        campaigns = data.get("results")

    if not isinstance(campaigns, list):
        return {
            "success": False,
            "http_status": response.status_code,
            "amazon_request_id": amazon_request_id,
            "response_json": data,
            "error_message": "Amazon campaign list response did not include campaigns/results list.",
        }

    if not campaigns:
        return {
            "success": False,
            "http_status": response.status_code,
            "amazon_request_id": amazon_request_id,
            "response_json": data,
            "error_message": f"Campaign {campaign_id} was not found in live Amazon campaign list.",
        }

    return {
        "success": True,
        "http_status": response.status_code,
        "amazon_request_id": amazon_request_id,
        "campaign": campaigns[0],
        "response_json": data,
        "error_message": None,
    }


def _extract_budget_from_campaign(campaign):
    if not isinstance(campaign, dict):
        return None

    budget_obj = campaign.get("budget")

    if isinstance(budget_obj, dict):
        for key in ["budget", "dailyBudget", "amount"]:
            value = _to_float(budget_obj.get(key))
            if value is not None:
                return value

    for key in ["budget", "dailyBudget", "daily_budget"]:
        value = _to_float(campaign.get(key))
        if value is not None:
            return value

    return None


def _send_campaign_update(profile_id, country_code, update_payload):
    """
    Sponsored Products v3 campaign update.

    Stores full Amazon response, HTTP status, and request ID.
    """
    headers = _build_headers(profile_id=profile_id, country_code=country_code)

    response = requests.put(
        f"{ADS_BASE_URL}/sp/campaigns",
        headers=headers,
        json={"campaigns": [update_payload]},
        timeout=30,
    )

    amazon_request_id = _extract_amazon_request_id(response)

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


def _resolve_budget(payload, mode, live_current_budget=None):
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
            "target_budget",
            "targetBudget",
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

    if current_budget is None:
        current_budget = _to_float(live_current_budget)

    percent = _to_float(
        _get_payload_value(
            payload,
            "percent",
            "percentage",
            "increase_percent",
            "decrease_percent",
            "change_percent",
            "suggested_budget_increase_percent",
            "suggestedBudgetIncreasePercent",
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
        return _round_budget(explicit_budget)

    if current_budget is None:
        # Some manual decisions may provide only a recommended final budget.
        return _round_budget(explicit_budget)

    if percent is not None:
        if mode == "INCREASE_BUDGET":
            return _round_budget(current_budget * (1 + percent / 100))
        if mode == "DECREASE_BUDGET":
            return _round_budget(current_budget * (1 - percent / 100))

    if amount is not None:
        if mode == "INCREASE_BUDGET":
            return _round_budget(current_budget + amount)
        if mode == "DECREASE_BUDGET":
            return _round_budget(current_budget - amount)

    return _round_budget(explicit_budget)


def _validate_budget_change(action, current_budget, new_budget):
    errors = []
    warnings = []

    if new_budget is None:
        errors.append("Could not resolve new budget.")
        return errors, warnings

    if new_budget < BUDGET_LIMITS["min_daily_budget"]:
        errors.append(
            f"New budget {new_budget} is below minimum {BUDGET_LIMITS['min_daily_budget']}."
        )

    if new_budget > BUDGET_LIMITS["max_daily_budget"]:
        errors.append(
            f"New budget {new_budget} exceeds maximum {BUDGET_LIMITS['max_daily_budget']}."
        )

    if current_budget is not None and current_budget > 0:
        change_pct = round(((new_budget - current_budget) / current_budget) * 100, 2)

        if change_pct > BUDGET_LIMITS["max_increase_percent"]:
            errors.append(
                f"Budget increase {change_pct}% exceeds max {BUDGET_LIMITS['max_increase_percent']}%."
            )

        if change_pct < -BUDGET_LIMITS["max_decrease_percent"]:
            errors.append(
                f"Budget decrease {abs(change_pct)}% exceeds max {BUDGET_LIMITS['max_decrease_percent']}%."
            )

        if abs(change_pct) < 0.01:
            warnings.append("Budget change is effectively zero.")

    return errors, warnings


def set_budget(profile_id, country_code, payload, dry_run=True, action="SET_BUDGET"):
    campaign_id = _get_campaign_id(payload)

    live_campaign_result = get_campaign_live(
        profile_id=profile_id,
        country_code=country_code,
        campaign_id=campaign_id,
    )

    if not live_campaign_result.get("success"):
        return {
            "success": False,
            "dry_run": dry_run,
            "http_status": live_campaign_result.get("http_status"),
            "amazon_request_id": live_campaign_result.get("amazon_request_id"),
            "action": action,
            "campaign_id": campaign_id,
            "response_json": live_campaign_result,
            "error_message": live_campaign_result.get("error_message"),
        }

    live_campaign = live_campaign_result.get("campaign")
    current_budget = _extract_budget_from_campaign(live_campaign)
    new_budget = _resolve_budget(payload, action, live_current_budget=current_budget)

    validation_errors, validation_warnings = _validate_budget_change(
        action=action,
        current_budget=current_budget,
        new_budget=new_budget,
    )

    if validation_errors:
        return {
            "success": False,
            "dry_run": dry_run,
            "action": action,
            "campaign_id": campaign_id,
            "current_budget": current_budget,
            "new_budget": new_budget,
            "budget_validation": {
                "ok": False,
                "errors": validation_errors,
                "warnings": validation_warnings,
                "limits": BUDGET_LIMITS,
            },
            "response_json": {
                "status": "BUDGET_VALIDATION_FAILED",
                "live_campaign": live_campaign,
            },
            "error_message": "; ".join(validation_errors),
        }

    change_pct = None
    if current_budget is not None and current_budget > 0:
        change_pct = round(((new_budget - current_budget) / current_budget) * 100, 2)

    update_payload = {
        "campaignId": campaign_id,
        "budget": {
            "budgetType": "DAILY",
            "budget": new_budget,
        },
    }

    budget_audit = {
        "current_budget": current_budget,
        "new_budget": new_budget,
        "budget_change": round(new_budget - current_budget, 2) if current_budget is not None else None,
        "budget_change_percent": change_pct,
        "budget_validation": {
            "ok": True,
            "errors": [],
            "warnings": validation_warnings,
            "limits": BUDGET_LIMITS,
        },
        "live_campaign_before": live_campaign,
    }

    if dry_run:
        return _dry_run_result(
            action,
            profile_id,
            country_code,
            campaign_id,
            update_payload,
            extra=budget_audit,
        )

    result = _send_campaign_update(profile_id, country_code, update_payload)
    result.update({
        "action": action,
        "campaign_id": campaign_id,
        "request_payload": update_payload,
        **budget_audit,
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
