from decision_history import save_decisions_to_history

from ai.decisions.pause_campaign import get_pause_campaign_decisions
from ai.decisions.negative_keyword import get_negative_keyword_decisions
from ai.decisions.harvest_keyword import get_harvest_keyword_decisions
from ai.decisions.reduce_bid import get_reduce_bid_decisions
from ai.decisions.increase_budget import get_increase_budget_decisions
from ai.decisions.shared import sort_decisions


def build_decisions():
    pause_decisions = get_pause_campaign_decisions()
    negative_decisions = get_negative_keyword_decisions()
    harvest_decisions = get_harvest_keyword_decisions()
    reduce_bid_decisions = get_reduce_bid_decisions()
    increase_budget_decisions = get_increase_budget_decisions()

    decisions = []
    decisions.extend(pause_decisions["decisions"])
    decisions.extend(negative_decisions["decisions"])
    decisions.extend(harvest_decisions["decisions"])
    decisions.extend(reduce_bid_decisions["decisions"])
    decisions.extend(increase_budget_decisions["decisions"])

    decisions = sort_decisions(decisions)

    history_result = save_decisions_to_history(decisions)

    return {
        "status": "OK",
        "count": len(decisions),
        "history_saved": history_result["saved"],
        "breakdown": {
            "pause_campaigns": pause_decisions["count"],
            "negative_keywords": negative_decisions["count"],
            "harvest_keywords": harvest_decisions["count"],
            "reduce_bids": reduce_bid_decisions["count"],
            "increase_budgets": increase_budget_decisions["count"],
        },
        "decisions": decisions,
    }
