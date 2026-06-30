"""
Business OS v3.8.0
Amazon Ads Execution Adapter with Bid Management

Supported live actions:
- PAUSE_CAMPAIGN
- RESUME_CAMPAIGN
- SET_BUDGET
- INCREASE_BUDGET
- DECREASE_BUDGET
- REDUCE_BID
- INCREASE_BID

Bid management in v3.8.0:
- Fetches current live keyword bid from Amazon before bid changes.
- Calculates before/after bid values.
- Enforces max % bid-change guardrails.
- Stores before/after bid values in ExecutionResult response_json.

Safety:
- Dry-run remains supported.
- Live execution still requires dry_run=false and confirm_live=true in execution_engine.py.
"""

import requests
from fastapi import HTTPException

from amazon_ads import ADS_BASE_URL, ads_headers


SP_CAMPAIGN_CONTENT_TYPE = "application/vnd.spCampaign.v3+json"
SP_KEYWORD_CONTENT_TYPE = "application/vnd.spKeyword.v3+json"

BUDGET_LIMITS = {
    "min_daily_budget": 1.00,
    "max_daily_budget": 500.00,
    "max_increase_percent": 50.00,
    "max_decrease_percent": 50.00,
}

BID_LIMITS = {
    "min_bid": 0.02,
    "max_bid": 10.00,
    "max_increase_percent": 25.00,
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


def _get_keyword_id(payload):
    value = _get_payload_value(payload, "keyword_id", "keywordId")
    return str(value) if value is not None else None


def _to_float(value):
    if value is None:
        return None

    try:
        return float(value)
    except Exception:
        return None


def _round_money(value):
    value = _to_float(value)
    if value is None:
        return None
    return round(value, 2)


def _campaign_headers(profile_id=None, country_code=None):
    headers = ads_headers(profile_id=profile_id, country_code=country_code)
    headers["Accept"] = SP_CAMPAIGN_CONTENT_TYPE
    headers["Content-Type"] = SP_CAMPAIGN_CONTENT_TYPE
    return headers


def _keyword_headers(profile_id=None, country_code=None):
    headers = ads_headers(profile_id=profile_id, country_code=country_code)
    headers["Accept"] = SP_KEYWORD_CONTENT_TYPE
    headers["Content-Type"] = SP_KEYWORD_CONTENT_TYPE
    return headers


def _extract_amazon_request_id(response):
    return (
        response.headers.get("x-amzn-requestid")
        or response.headers.get("x-amz-request-id")
        or response.headers.get("x-amzn-RequestId")
    )


def _dry_run_result(action, profile_id, country_code, resource_id, update_payload, extra=None):
    extra = extra or {}

    return {
        "success": True,
        "dry_run": True,
        "http_status": None,
        "amazon_request_id": None,
        "action": action,
        "profile_id": profile_id,
        "country_code": country_code,
        "resource_id": resource_id,
        "request_payload": update_payload,
        **extra,
        "response_json": {
            "mode": "dry_run",
            "message": "No Amazon Ads changes were made.",
            "action": action,
            "resource_id": resource_id,
            "request_payload": update_payload,
            **extra,
        },
    }


def get_campaign_live(profile_id, country_code, campaign_id):
    headers = _campaign_headers(profile_id=profile_id, country_code=country_code)

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

    if not isinstance(campaigns, list) or not campaigns:
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


def get_keyword_live(profile_id, country_code, keyword_id):
    headers = _keyword_headers(profile_id=profile_id, country_code=country_code)

    body = {
        "keywordIdFilter": {
            "include": [str(keyword_id)]
        },
        "maxResults": 10,
    }

    response = requests.post(
        f"{ADS_BASE_URL}/sp/keywords/list",
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

    keywords = data.get("keywords")
    if not isinstance(keywords, list):
        keywords = data.get("results")

    if not isinstance(keywords, list) or not keywords:
        return {
            "success": False,
            "http_status": response.status_code,
            "amazon_request_id": amazon_request_id,
            "response_json": data,
            "error_message": f"Keyword {keyword_id} was not found in live Amazon keyword list.",
        }

    return {
        "success": True,
        "http_status": response.status_code,
        "amazon_request_id": amazon_request_id,
        "keyword": keywords[0],
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


def _extract_bid_from_keyword(keyword):
    if not isinstance(keyword, dict):
        return None

    for key in ["bid", "defaultBid"]:
        value = _to_float(keyword.get(key))
        if value is not None:
            return value

    bid_obj = keyword.get("bid")
    if isinstance(bid_obj, dict):
        for key in ["bid", "amount"]:
            value = _to_float(bid_obj.get(key))
            if value is not None:
                return value

    return None


def _send_campaign_update(profile_id, country_code, update_payload):
    headers = _campaign_headers(profile_id=profile_id, country_code=country_code)

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


def _send_keyword_update(profile_id, country_code, update_payload):
    headers = _keyword_headers(profile_id=profile_id, country_code=country_code)

    response = requests.put(
        f"{ADS_BASE_URL}/sp/keywords",
        headers=headers,
        json={"keywords": [update_payload]},
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
        return _round_money(explicit_budget)

    if current_budget is None:
        return _round_money(explicit_budget)

    if percent is not None:
        if mode == "INCREASE_BUDGET":
            return _round_money(current_budget * (1 + percent / 100))
        if mode == "DECREASE_BUDGET":
            return _round_money(current_budget * (1 - percent / 100))

    if amount is not None:
        if mode == "INCREASE_BUDGET":
            return _round_money(current_budget + amount)
        if mode == "DECREASE_BUDGET":
            return _round_money(current_budget - amount)

    return _round_money(explicit_budget)


def _resolve_bid(payload, mode, live_current_bid=None):
    explicit_bid = _to_float(
        _get_payload_value(
            payload,
            "new_bid",
            "newBid",
            "bid",
            "target_bid",
            "targetBid",
            "recommended_bid",
            "recommendedBid",
        )
    )

    current_bid = _to_float(
        _get_payload_value(
            payload,
            "current_bid",
            "currentBid",
            "existing_bid",
            "existingBid",
        )
    )

    if current_bid is None:
        current_bid = _to_float(live_current_bid)

    percent = _to_float(
        _get_payload_value(
            payload,
            "percent",
            "percentage",
            "reduce_percent",
            "reduction_percent",
            "increase_percent",
            "change_percent",
            "decrease_percent",
            "suggested_bid_reduction_percent",
            "suggested_bid_increase_percent",
            "suggestedBidReductionPercent",
            "suggestedBidIncreasePercent",
        )
    )

    amount = _to_float(
        _get_payload_value(
            payload,
            "amount",
            "change_amount",
            "reduce_amount",
            "increase_amount",
            "decrease_amount",
        )
    )

    if mode == "SET_BID":
        return _round_money(explicit_bid)

    if current_bid is None:
        return _round_money(explicit_bid)

    if percent is not None:
        percent = abs(percent)
        if mode == "REDUCE_BID":
            return _round_money(current_bid * (1 - percent / 100))
        if mode == "INCREASE_BID":
            return _round_money(current_bid * (1 + percent / 100))

    if amount is not None:
        amount = abs(amount)
        if mode == "REDUCE_BID":
            return _round_money(current_bid - amount)
        if mode == "INCREASE_BID":
            return _round_money(current_bid + amount)

    return _round_money(explicit_bid)

def _validate_budget_change(current_budget, new_budget):
    errors = []
    warnings = []

    if new_budget is None:
        errors.append("Could not resolve new budget.")
        return errors, warnings

    if new_budget < BUDGET_LIMITS["min_daily_budget"]:
        errors.append(f"New budget {new_budget} is below minimum {BUDGET_LIMITS['min_daily_budget']}.")

    if new_budget > BUDGET_LIMITS["max_daily_budget"]:
        errors.append(f"New budget {new_budget} exceeds maximum {BUDGET_LIMITS['max_daily_budget']}.")

    if current_budget is not None and current_budget > 0:
        change_pct = round(((new_budget - current_budget) / current_budget) * 100, 2)

        if change_pct > BUDGET_LIMITS["max_increase_percent"]:
            errors.append(f"Budget increase {change_pct}% exceeds max {BUDGET_LIMITS['max_increase_percent']}%.")

        if change_pct < -BUDGET_LIMITS["max_decrease_percent"]:
            errors.append(f"Budget decrease {abs(change_pct)}% exceeds max {BUDGET_LIMITS['max_decrease_percent']}%.")

        if abs(change_pct) < 0.01:
            warnings.append("Budget change is effectively zero.")

    return errors, warnings


def _validate_bid_change(current_bid, new_bid):
    errors = []
    warnings = []

    if new_bid is None:
        errors.append("Could not resolve new bid.")
        return errors, warnings

    if new_bid < BID_LIMITS["min_bid"]:
        errors.append(f"New bid {new_bid} is below minimum {BID_LIMITS['min_bid']}.")

    if new_bid > BID_LIMITS["max_bid"]:
        errors.append(f"New bid {new_bid} exceeds maximum {BID_LIMITS['max_bid']}.")

    if current_bid is not None and current_bid > 0:
        change_pct = round(((new_bid - current_bid) / current_bid) * 100, 2)

        if change_pct > BID_LIMITS["max_increase_percent"]:
            errors.append(f"Bid increase {change_pct}% exceeds max {BID_LIMITS['max_increase_percent']}%.")

        if change_pct < -BID_LIMITS["max_decrease_percent"]:
            errors.append(f"Bid decrease {abs(change_pct)}% exceeds max {BID_LIMITS['max_decrease_percent']}%.")

        if abs(change_pct) < 0.01:
            warnings.append("Bid change is effectively zero.")

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
        return _dry_run_result(action, profile_id, country_code, campaign_id, update_payload, extra=budget_audit)

    result = _send_campaign_update(profile_id, country_code, update_payload)
    result.update({
        "action": action,
        "campaign_id": campaign_id,
        "request_payload": update_payload,
        **budget_audit,
    })
    return result


def change_bid(profile_id, country_code, payload, dry_run=True, action="REDUCE_BID"):
    keyword_id = _get_keyword_id(payload)

    live_keyword_result = get_keyword_live(
        profile_id=profile_id,
        country_code=country_code,
        keyword_id=keyword_id,
    )

    if not live_keyword_result.get("success"):
        return {
            "success": False,
            "dry_run": dry_run,
            "http_status": live_keyword_result.get("http_status"),
            "amazon_request_id": live_keyword_result.get("amazon_request_id"),
            "action": action,
            "keyword_id": keyword_id,
            "response_json": live_keyword_result,
            "error_message": live_keyword_result.get("error_message"),
        }

    live_keyword = live_keyword_result.get("keyword")
    current_bid = _extract_bid_from_keyword(live_keyword)
    new_bid = _resolve_bid(payload, action, live_current_bid=current_bid)

    validation_errors, validation_warnings = _validate_bid_change(
        current_bid=current_bid,
        new_bid=new_bid,
    )

    if validation_errors:
        return {
            "success": False,
            "dry_run": dry_run,
            "action": action,
            "keyword_id": keyword_id,
            "current_bid": current_bid,
            "new_bid": new_bid,
            "bid_validation": {
                "ok": False,
                "errors": validation_errors,
                "warnings": validation_warnings,
                "limits": BID_LIMITS,
            },
            "response_json": {
                "status": "BID_VALIDATION_FAILED",
                "live_keyword": live_keyword,
            },
            "error_message": "; ".join(validation_errors),
        }

    change_pct = None
    if current_bid is not None and current_bid > 0:
        change_pct = round(((new_bid - current_bid) / current_bid) * 100, 2)

    update_payload = {
        "keywordId": keyword_id,
        "bid": new_bid,
    }

    bid_audit = {
        "current_bid": current_bid,
        "new_bid": new_bid,
        "bid_change": round(new_bid - current_bid, 2) if current_bid is not None else None,
        "bid_change_percent": change_pct,
        "bid_validation": {
            "ok": True,
            "errors": [],
            "warnings": validation_warnings,
            "limits": BID_LIMITS,
        },
        "live_keyword_before": live_keyword,
    }

    if dry_run:
        return _dry_run_result(action, profile_id, country_code, keyword_id, update_payload, extra=bid_audit)

    result = _send_keyword_update(profile_id, country_code, update_payload)
    result.update({
        "action": action,
        "keyword_id": keyword_id,
        "request_payload": update_payload,
        **bid_audit,
    })
    return result


def reduce_bid(profile_id, country_code, payload, dry_run=True):
    return change_bid(profile_id, country_code, payload, dry_run=dry_run, action="REDUCE_BID")


def increase_bid(profile_id, country_code, payload, dry_run=True):
    return change_bid(profile_id, country_code, payload, dry_run=dry_run, action="INCREASE_BID")

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

    if action == "REDUCE_BID":
        return reduce_bid(profile_id, country_code, payload, dry_run=dry_run)

    if action == "INCREASE_BID":
        return increase_bid(profile_id, country_code, payload, dry_run=dry_run)

    raise HTTPException(
        status_code=400,
        detail=f"Unsupported Amazon live execution action: {action}",
    )
