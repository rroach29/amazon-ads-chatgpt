"""
Business OS v8.3
Optimizer Registry with Manifests

Mission Control and planners should not know individual optimizer internals.
They ask the registry for optimizer manifests and run outputs.
"""

from business_data_context import resolve_data_context
from optimizers.keyword_optimizer import KeywordOptimizer
from optimizers.bid_optimizer import BidOptimizer
from optimizers.budget_optimizer import BudgetOptimizer
from optimizers.opportunity_queue import sort_opportunities


REGISTERED_OPTIMIZERS = [
    KeywordOptimizer,
    BidOptimizer,
    BudgetOptimizer,
]


def optimizer_manifests():
    return [optimizer.manifest() for optimizer in REGISTERED_OPTIMIZERS]


def list_optimizers():
    manifests = optimizer_manifests()
    return {
        "status": "OK",
        "schema_version": "8.3",
        "count": len(REGISTERED_OPTIMIZERS),
        "optimizers": manifests,
        "decision_types": sorted({dt for manifest in manifests for dt in manifest.get("decision_types", [])}),
        "narrative": "Optimizers are registered through v8.3 manifests with provenance metadata.",
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
        "schema_version": "8.3",
        "context": context,
        "optimizer_count": len(results),
        "optimizer_manifests": optimizer_manifests(),
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
