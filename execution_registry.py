"""
Business OS v3.6.1
Execution Action Registry

Central registry for actions supported by the execution planner and batch engine.
"""

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
        "supported": False,
        "live_supported": False,
        "platform": "amazon_ads",
        "resource_type": "target",
        "requires_campaign_identity": False,
        "rollback_action": None,
        "reason": "Bid execution is planned for a later release.",
    },
    "SET_BID": {
        "action": "SET_BID",
        "supported": False,
        "live_supported": False,
        "platform": "amazon_ads",
        "resource_type": "target",
        "requires_campaign_identity": False,
        "rollback_action": None,
        "reason": "Bid execution is planned for a later release.",
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
