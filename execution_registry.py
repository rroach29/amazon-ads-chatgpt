"""
Business OS v3.8.0
Execution Registry

Adds live support for REDUCE_BID.
"""

from amazon_execution import execute_amazon_action


ACTION_REGISTRY = {
    "PAUSE_CAMPAIGN": {
        "action": "PAUSE_CAMPAIGN",
        "supported": True,
        "live_supported": True,
        "platform": "amazon_ads",
        "resource_type": "campaign",
        "requires_campaign_identity": True,
        "rollback_action": "RESUME_CAMPAIGN",
    },
    "RESUME_CAMPAIGN": {
        "action": "RESUME_CAMPAIGN",
        "supported": True,
        "live_supported": True,
        "platform": "amazon_ads",
        "resource_type": "campaign",
        "requires_campaign_identity": True,
        "rollback_action": "PAUSE_CAMPAIGN",
    },
    "SET_BUDGET": {
        "action": "SET_BUDGET",
        "supported": True,
        "live_supported": True,
        "platform": "amazon_ads",
        "resource_type": "campaign",
        "requires_campaign_identity": True,
        "rollback_action": None,
    },
    "INCREASE_BUDGET": {
        "action": "INCREASE_BUDGET",
        "supported": True,
        "live_supported": True,
        "platform": "amazon_ads",
        "resource_type": "campaign",
        "requires_campaign_identity": True,
        "rollback_action": None,
    },
    "DECREASE_BUDGET": {
        "action": "DECREASE_BUDGET",
        "supported": True,
        "live_supported": True,
        "platform": "amazon_ads",
        "resource_type": "campaign",
        "requires_campaign_identity": True,
        "rollback_action": None,
    },
    "REDUCE_BID": {
        "action": "REDUCE_BID",
        "supported": True,
        "live_supported": True,
        "platform": "amazon_ads",
        "resource_type": "keyword",
        "requires_campaign_identity": True,
        "requires_keyword_id": True,
        "rollback_action": None,
    },

    "INCREASE_BID": {
        "action": "INCREASE_BID",
        "supported": True,
        "live_supported": True,
        "platform": "amazon_ads",
        "resource_type": "keyword",
        "requires_campaign_identity": True,
        "requires_keyword_id": True,
        "rollback_action": None,
    },
    "SET_BID": {
        "action": "SET_BID",
        "supported": False,
        "live_supported": False,
        "platform": "amazon_ads",
        "resource_type": "keyword",
        "requires_campaign_identity": True,
        "requires_keyword_id": True,
        "rollback_action": None,
        "reason": "Exact set-bid execution is planned after reduce-bid is verified.",
    },
    "ADD_NEGATIVE_KEYWORD": {
        "action": "ADD_NEGATIVE_KEYWORD",
        "supported": False,
        "live_supported": False,
        "platform": "amazon_ads",
        "resource_type": "keyword",
        "requires_campaign_identity": True,
        "rollback_action": None,
        "reason": "Keyword execution is planned for a later release.",
    },
    "HARVEST_KEYWORD": {
        "action": "HARVEST_KEYWORD",
        "supported": False,
        "live_supported": False,
        "platform": "amazon_ads",
        "resource_type": "keyword",
        "requires_campaign_identity": True,
        "rollback_action": None,
        "reason": "Keyword harvesting execution is planned for a later release.",
    },
}


def get_action_metadata(action):
    return ACTION_REGISTRY.get(
        action,
        {
            "action": action,
            "supported": False,
            "live_supported": False,
            "platform": "amazon_ads",
            "resource_type": None,
            "requires_campaign_identity": False,
            "rollback_action": None,
            "reason": "Action is not registered.",
        },
    )


def list_execution_actions():
    return {
        "status": "OK",
        "actions": list(ACTION_REGISTRY.values()),
        "live_supported": [
            name for name, metadata in ACTION_REGISTRY.items()
            if metadata.get("live_supported")
        ],
        "dry_run_default": True,
        "live_requires": {
            "dry_run": False,
            "confirm_live": True,
        },
    }


def execute_registered_action(action, profile_id, country_code, payload, dry_run=True):
    metadata = get_action_metadata(action)

    if not metadata.get("supported"):
        return {
            "success": False,
            "dry_run": dry_run,
            "action": action,
            "error_message": metadata.get("reason") or f"Action {action} is not supported.",
            "response_json": {
                "status": "UNSUPPORTED_ACTION",
                "metadata": metadata,
            },
        }

    if metadata.get("platform") != "amazon_ads":
        return {
            "success": False,
            "dry_run": dry_run,
            "action": action,
            "error_message": f"Unsupported execution platform: {metadata.get('platform')}",
            "response_json": {
                "status": "UNSUPPORTED_PLATFORM",
                "metadata": metadata,
            },
        }

    return execute_amazon_action(
        action=action,
        profile_id=profile_id,
        country_code=country_code,
        payload=payload,
        dry_run=dry_run,
    )
