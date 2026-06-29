from amazon.campaigns import pause_campaign


def execute_pause_campaign(decision):
    payload = decision.payload or {}
    return pause_campaign(payload)


def execute_add_negative_keyword(decision):
    payload = decision.payload or {}

    return {
        "status": "SIMULATED",
        "decision": decision.decision,
        "message": f"Would add negative keyword: {payload.get('search_term')}",
        "payload": payload,
    }


def execute_harvest_keyword(decision):
    payload = decision.payload or {}

    return {
        "status": "SIMULATED",
        "decision": decision.decision,
        "message": f"Would harvest keyword: {payload.get('keyword')}",
        "payload": payload,
    }


def execute_reduce_bid(decision):
    payload = decision.payload or {}

    return {
        "status": "SIMULATED",
        "decision": decision.decision,
        "message": (
            f"Would reduce bid by "
            f"{payload.get('suggested_bid_reduction_percent')}%"
        ),
        "payload": payload,
    }


def execute_increase_budget(decision):
    payload = decision.payload or {}

    return {
        "status": "SIMULATED",
        "decision": decision.decision,
        "message": (
            f"Would increase budget by "
            f"{payload.get('suggested_budget_increase_percent')}%"
        ),
        "payload": payload,
    }


EXECUTION_HANDLERS = {
    "PAUSE_CAMPAIGN": execute_pause_campaign,
    "ADD_NEGATIVE_KEYWORD": execute_add_negative_keyword,
    "HARVEST_KEYWORD": execute_harvest_keyword,
    "REDUCE_BID": execute_reduce_bid,
    "INCREASE_BUDGET": execute_increase_budget,
}
