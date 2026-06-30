"""
Business OS v3.6.0
Universal Execution Action Registry

Central registry for executable actions. This keeps batch/planner/queue code
platform-neutral while current live handlers continue to use the Amazon adapter
through execution_engine.py.
"""

from amazon_execution import execute_amazon_action


CAMPAIGN_ACTIONS = {
    "PAUSE_CAMPAIGN",
    "RESUME_CAMPAIGN",
    "SET_BUDGET",
    "INCREASE_BUDGET",
    "DECREASE_BUDGET",
}

LIVE_SUPPORTED_ACTIONS = set(CAMPAIGN_ACTIONS)

SUPPORTED_ACTIONS = set(CAMPAIGN_ACTIONS) | {
    "SET_BID",
    "ADD_NEGATIVE_KEYWORD",
    "HARVEST_KEYWORD",
    "PROMOTE_TO_EXACT",
}


def get_action_metadata(action):
    action = str(action or "").upper()

    metadata = {
        "action": action,
        "supported": action in SUPPORTED_ACTIONS,
        "live_supported": action in LIVE_SUPPORTED_ACTIONS,
        "platform": "amazon_ads",
        "resource_type": None,
        "requires_campaign_identity": False,
        "rollback_action": None,
    }

    if action in CAMPAIGN_ACTIONS:
        metadata["resource_type"] = "campaign"
        metadata["requires_campaign_identity"] = True

    if action == "PAUSE_CAMPAIGN":
        metadata["rollback_action"] = "RESUME_CAMPAIGN"
    elif action == "RESUME_CAMPAIGN":
        metadata["rollback_action"] = "PAUSE_CAMPAIGN"

    return metadata


def list_actions():
    return {
        "status": "OK",
        "count": len(SUPPORTED_ACTIONS),
        "live_supported_count": len(LIVE_SUPPORTED_ACTIONS),
        "actions": [get_action_metadata(action) for action in sorted(SUPPORTED_ACTIONS)],
    }


def execute_registered_action(action, profile_id, country_code, payload, dry_run=True):
    """
    Dispatch execution to the platform adapter.

    Today: Amazon Ads campaign actions.
    Future: Shopify, Meta, Google Ads, Seller Central adapters.
    """
    action = str(action or "").upper()
    metadata = get_action_metadata(action)

    if not metadata["supported"]:
        return {
            "success": False,
            "dry_run": dry_run,
            "action": action,
            "error_message": f"Unsupported action: {action}",
            "response_json": {"metadata": metadata},
        }

    if action in CAMPAIGN_ACTIONS:
        return execute_amazon_action(
            action=action,
            profile_id=profile_id,
            country_code=country_code,
            payload=payload,
            dry_run=dry_run,
        )

    return {
        "success": False,
        "dry_run": dry_run,
        "action": action,
        "error_message": f"Action is registered but live handler is not implemented yet: {action}",
        "response_json": {"metadata": metadata},
    }
