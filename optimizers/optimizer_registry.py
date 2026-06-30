"""
Business OS v6.1.0
Optimizer Registry

Mission Control and planners should not know individual optimizer internals.
They ask the registry to run all registered optimizers and receive one ranked
opportunity queue.
"""

from business_data_context import resolve_data_context
from optimizers.keyword_optimizer import KeywordOptimizer
from optimizers.bid_optimizer import BidOptimizer
from optimizers.opportunity_queue import sort_opportunities


REGISTERED_OPTIMIZERS = [
    KeywordOptimizer,
    BidOptimizer,
]


def list_optimizers():
    return {
        "status": "OK",
        "count": len(REGISTERED_OPTIMIZERS),
        "optimizers": [
            {
                "name": optimizer.name,
                "version": getattr(optimizer, "version", None),
                "decision_types": optimizer.decision_types,
            }
            for optimizer in REGISTERED_OPTIMIZERS
        ],
    }


def run_optimizer(name, context=None):
    for optimizer_class in REGISTERED_OPTIMIZERS:
        if optimizer_class.name == name:
            return optimizer_class(context=context).run()

    return {
        "status": "NOT_FOUND",
        "message": f"Optimizer not found: {name}",
    }


def run_all_optimizers(window="latest", country_code=None, profile_id=None):
    context = resolve_data_context(
        window=window,
        country_code=country_code,
        profile_id=profile_id,
    )

    results = []
    opportunities = []
    decisions = []

    for optimizer_class in REGISTERED_OPTIMIZERS:
        result = optimizer_class(context=context).run()
        results.append(result)
        opportunities.extend(result.get("opportunities", []))
        decisions.extend(result.get("decisions", []))

    return {
        "status": "OK",
        "context": context,
        "optimizer_count": len(results),
        "optimizers": results,
        "opportunity_count": len(opportunities),
        "decision_count": len(decisions),
        "opportunity_queue": sort_opportunities(opportunities),
        "decisions": decisions,
        "metrics": {
            "optimizer_statuses": [item.get("metrics") for item in results],
            "error_count": len([item for item in results if item.get("status") == "ERROR"]),
        },
    }
