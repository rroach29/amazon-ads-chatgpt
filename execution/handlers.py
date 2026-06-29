import os

try:
    from amazon.campaigns import pause_campaign as amazon_pause_campaign
except Exception:
    amazon_pause_campaign = None


def is_dry_run():
    value = os.getenv("AMAZON_EXECUTION_DRY_RUN", "true")
    return value.lower() not in {"false", "0", "no"}


def _base_result(decision, action, message, payload, undo_supported=False, undo_action=None, amazon_request=None, amazon_response=None):
    dry_run = is_dry_run()

    return {
        "status": "SIMULATED" if dry_run else "SUCCESS",
        "dry_run": dry_run,
        "action": action,
        "decision": decision.decision,
        "message": message,
        "payload": payload,
        "undo_supported": undo_supported,
        "undo_action": undo_action,
        "amazon_request": amazon_request or {},
        "amazon_response": amazon_response or {},
    }


def execute_pause_campaign(decision):
    payload = decision.payload or {}
    campaign_id = payload.get("campaign_id")
    campaign_name = payload.get("campaign_name")
    dry_run = is_dry_run()

    if amazon_pause_campaign:
        amazon_result = amazon_pause_campaign(payload, dry_run=dry_run)
    else:
        amazon_result = {
            "dry_run": dry_run,
            "action": "PAUSE_CAMPAIGN",
            "message": "amazon.campaigns.pause_campaign is not available.",
            "payload": payload,
        }

    status = "SIMULATED" if dry_run else amazon_result.get("status", "SUCCESS")

    return {
        "status": status,
        "dry_run": dry_run,
        "action": "PAUSE_CAMPAIGN",
        "decision": decision.decision,
        "message": (
            f"Would pause campaign: {campaign_name}"
            if dry_run
            else f"Paused campaign: {campaign_name}"
        ),
        "payload": payload,
        "undo_supported": True,
        "undo_action": "RESUME_CAMPAIGN",
        "amazon_request": {
            "campaign_id": campaign_id,
            "state": "PAUSED",
        },
        "amazon_response": amazon_result,
    }


def execute_add_negative_keyword(decision):
    payload = decision.payload or {}

    return _base_result(
        decision=decision,
        action="ADD_NEGATIVE_KEYWORD",
        message=f"Would add negative keyword: {payload.get('search_term')}",
        payload=payload,
        undo_supported=True,
        undo_action="REMOVE_NEGATIVE_KEYWORD",
        amazon_request={
            "campaign_id": payload.get("campaign_id"),
            "ad_group_id": payload.get("ad_group_id"),
            "keyword_text": payload.get("search_term"),
            "match_type": payload.get("suggested_negative_match_type"),
        },
    )


def execute_harvest_keyword(decision):
    payload = decision.payload or {}

    return _base_result(
        decision=decision,
        action="HARVEST_KEYWORD",
        message=f"Would harvest keyword: {payload.get('keyword')}",
        payload=payload,
        undo_supported=True,
        undo_action="PAUSE_HARVESTED_KEYWORD",
        amazon_request={
            "target_campaign_name": payload.get("target_campaign_name"),
            "keyword_text": payload.get("keyword"),
            "match_type": "EXACT",
            "suggested_bid": payload.get("suggested_bid"),
        },
    )


def execute_reduce_bid(decision):
    payload = decision.payload or {}

    return _base_result(
        decision=decision,
        action="REDUCE_BID",
        message=(
            f"Would reduce bid by "
            f"{payload.get('suggested_bid_reduction_percent')}%"
        ),
        payload=payload,
        undo_supported=True,
        undo_action="RESTORE_PREVIOUS_BID",
        amazon_request={
            "campaign_id": payload.get("campaign_id"),
            "ad_group_id": payload.get("ad_group_id"),
            "keyword": payload.get("keyword"),
            "reduction_percent": payload.get("suggested_bid_reduction_percent"),
        },
    )


def execute_increase_budget(decision):
    payload = decision.payload or {}

    return _base_result(
        decision=decision,
        action="INCREASE_BUDGET",
        message=(
            f"Would increase budget by "
            f"{payload.get('suggested_budget_increase_percent')}%"
        ),
        payload=payload,
        undo_supported=True,
        undo_action="RESTORE_PREVIOUS_BUDGET",
        amazon_request={
            "campaign_id": payload.get("campaign_id"),
            "increase_percent": payload.get("suggested_budget_increase_percent"),
        },
    )


EXECUTION_HANDLERS = {
    "PAUSE_CAMPAIGN": execute_pause_campaign,
    "ADD_NEGATIVE_KEYWORD": execute_add_negative_keyword,
    "HARVEST_KEYWORD": execute_harvest_keyword,
    "REDUCE_BID": execute_reduce_bid,
    "INCREASE_BUDGET": execute_increase_budget,
}
