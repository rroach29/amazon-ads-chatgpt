"""
Business OS v6.1.1
Decision Engine

Change:
Generated decisions are persisted before being returned so every item in
/business-os/decisions has a stable decision_id immediately.
"""

from decision_history import save_decisions_to_history

from business_data_context import resolve_data_context
from ai.decisions.pause_campaign import get_pause_campaign_decisions
from ai.decisions.negative_keyword import get_negative_keyword_decisions
from ai.decisions.harvest_keyword import get_harvest_keyword_decisions
from ai.decisions.reduce_bid import get_reduce_bid_decisions
from ai.decisions.increase_budget import get_increase_budget_decisions
from ai.decisions.shared import sort_decisions

try:
    from optimizers.optimizer_registry import run_all_optimizers
except Exception:
    run_all_optimizers = None


def _optimizer_decisions(context):
    """
    Use the v6 optimizer platform when available. Fall back silently for older
    deployments so this module remains backward compatible.
    """
    if not run_all_optimizers:
        return None

    try:
        try:
            result = run_all_optimizers(context=context)
        except TypeError:
            result = run_all_optimizers(
                window=context.get("window", "latest"),
                country_code=context.get("country_code"),
                profile_id=context.get("profile_id"),
            )

        decisions = result.get("decisions") if isinstance(result, dict) else None
        return decisions if isinstance(decisions, list) else None
    except Exception:
        return None


def _legacy_decisions(context):
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

    return decisions, {
        "pause_campaigns": pause_decisions["count"],
        "negative_keywords": negative_decisions["count"],
        "harvest_keywords": harvest_decisions["count"],
        "reduce_bids": reduce_bid_decisions["count"],
        "increase_budgets": increase_budget_decisions["count"],
    }


def _breakdown(decisions):
    counts = {}
    for decision in decisions:
        decision_type = decision.get("decision")
        counts[decision_type] = counts.get(decision_type, 0) + 1
    return counts


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

    optimizer_generated = _optimizer_decisions(context)

    if optimizer_generated is not None:
        decisions = optimizer_generated
        breakdown = _breakdown(decisions)
        source = "optimizer_registry"
    else:
        decisions, breakdown = _legacy_decisions(context)
        source = "legacy_decision_modules"

    decisions = sort_decisions(decisions)

    history_result = save_decisions_to_history(decisions)
    persisted_decisions = history_result.get("items", decisions)

    return {
        "status": "OK",
        "data_context": context,
        "decision_source": source,
        "count": len(persisted_decisions),
        "history_saved": history_result.get("saved", 0),
        "history_updated": history_result.get("updated", 0),
        "history_unchanged": history_result.get("unchanged", 0),
        "decision_ids": history_result.get("ids", []),
        "breakdown": breakdown,
        "decisions": persisted_decisions,
    }
