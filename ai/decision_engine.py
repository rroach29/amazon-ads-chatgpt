from decision_history import save_decisions_to_history

from business_data_context import resolve_data_context
from ai.decisions.pause_campaign import get_pause_campaign_decisions
from ai.decisions.negative_keyword import get_negative_keyword_decisions
from ai.decisions.harvest_keyword import get_harvest_keyword_decisions
from ai.decisions.reduce_bid import get_reduce_bid_decisions
from ai.decisions.increase_budget import get_increase_budget_decisions
from ai.decisions.shared import sort_decisions


def build_decisions(
    window="latest",
    country_code=None,
    profile_id=None,
    start_date=None,
    end_date=None,
):
    context = resolve_data_context(
        window=window,
        country_code=country_code,
        profile_id=profile_id,
        start_date=start_date,
        end_date=end_date,
    )

    pause_decisions = get_pause_campaign_decisions(data_context=context)
    negative_decisions = get_negative_keyword_decisions(data_context=context)
    harvest_decisions = get_harvest_keyword_decisions()
    reduce_bid_decisions = get_reduce_bid_decisions(data_context=context)
    increase_budget_decisions = get_increase_budget_decisions(data_context=context)

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
        "data_context": context,
        "count": len(decisions),
        "history_saved": history_result.get("saved", 0),
        "history_updated": history_result.get("updated", 0),
        "breakdown": {
            "pause_campaigns": pause_decisions["count"],
            "negative_keywords": negative_decisions["count"],
            "harvest_keywords": harvest_decisions["count"],
            "reduce_bids": reduce_bid_decisions["count"],
            "increase_budgets": increase_budget_decisions["count"],
        },
        "decisions": decisions,
    }
