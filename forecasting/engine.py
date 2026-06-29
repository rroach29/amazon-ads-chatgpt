from business_context import get_business_os_context
from decision_history import get_decision_history

try:
    from learning.summary import get_learning_summary
except Exception:  # pragma: no cover
    get_learning_summary = None

from forecasting.score import calculate_business_score


def _safe_float(value, default=0):
    try:
        return float(value or default)
    except Exception:
        return default


def _safe_int(value, default=0):
    try:
        return int(value or default)
    except Exception:
        return default


def _get_dashboard_summary(context):
    dashboard = context.get("dashboard", {}) if isinstance(context, dict) else {}
    return dashboard.get("summary", {}) or {}


def _get_open_decisions(limit=100):
    result = get_decision_history(status="OPEN", limit=limit)
    return result.get("items", []) or []


def _decision_impact(decisions):
    return sum(_safe_float(d.get("estimated_monthly_impact")) for d in decisions)


def _decisions_by_type(decisions):
    breakdown = {}
    for decision in decisions:
        decision_type = decision.get("decision") or "UNKNOWN"
        breakdown.setdefault(decision_type, {"count": 0, "estimated_monthly_impact": 0})
        breakdown[decision_type]["count"] += 1
        breakdown[decision_type]["estimated_monthly_impact"] += _safe_float(
            decision.get("estimated_monthly_impact")
        )

    for item in breakdown.values():
        item["estimated_monthly_impact"] = round(item["estimated_monthly_impact"], 2)

    return breakdown


def _learning_accuracy():
    if not get_learning_summary:
        return None

    try:
        summary = get_learning_summary()
        return summary.get("accuracy_percent") or summary.get("overall_accuracy")
    except Exception:
        return None


def forecast_open_decisions():
    context = get_business_os_context()
    summary = _get_dashboard_summary(context)
    decisions = _get_open_decisions(limit=100)

    spend = _safe_float(summary.get("spend"))
    sales = _safe_float(summary.get("sales"))
    acos = summary.get("acos")
    roas = summary.get("roas")

    estimated_monthly_impact = _decision_impact(decisions)
    learning_accuracy = _learning_accuracy()

    # Conservative starting assumptions until real learning data matures.
    confidence = learning_accuracy if learning_accuracy is not None else 75
    confidence_multiplier = confidence / 100

    adjusted_impact = estimated_monthly_impact * confidence_multiplier

    # Classify impact: waste reducers reduce spend, growth actions increase sales.
    waste_reduction_types = {"PAUSE_CAMPAIGN", "ADD_NEGATIVE_KEYWORD", "REDUCE_BID"}
    growth_types = {"HARVEST_KEYWORD", "INCREASE_BUDGET", "INCREASE_BID", "SCALE_CAMPAIGN"}

    estimated_spend_reduction = 0
    estimated_sales_lift = 0

    for decision in decisions:
        impact = _safe_float(decision.get("estimated_monthly_impact")) * confidence_multiplier
        decision_type = decision.get("decision")

        if decision_type in waste_reduction_types:
            estimated_spend_reduction += impact
        elif decision_type in growth_types:
            estimated_sales_lift += impact
        else:
            estimated_sales_lift += impact * 0.5

    projected_spend = max(0, spend - estimated_spend_reduction)
    projected_sales = max(0, sales + estimated_sales_lift)
    projected_acos = (projected_spend / projected_sales) if projected_sales > 0 else None
    projected_roas = (projected_sales / projected_spend) if projected_spend > 0 else None

    business_score = calculate_business_score(
        acos=acos,
        roas=roas,
        open_decisions=len(decisions),
        learning_accuracy=learning_accuracy,
        estimated_waste=estimated_spend_reduction,
        sales=sales,
    )

    return {
        "status": "OK",
        "title": "Business OS Forecast",
        "scenario": "OPEN_DECISIONS",
        "decision_count": len(decisions),
        "confidence": round(confidence, 1),
        "current": {
            "spend": spend,
            "sales": sales,
            "acos": acos,
            "roas": roas,
        },
        "forecast": {
            "estimated_monthly_impact": round(estimated_monthly_impact, 2),
            "confidence_adjusted_impact": round(adjusted_impact, 2),
            "estimated_spend_reduction": round(estimated_spend_reduction, 2),
            "estimated_sales_lift": round(estimated_sales_lift, 2),
            "projected_spend": round(projected_spend, 2),
            "projected_sales": round(projected_sales, 2),
            "projected_acos": round(projected_acos, 4) if projected_acos is not None else None,
            "projected_roas": round(projected_roas, 4) if projected_roas is not None else None,
        },
        "business_score": business_score,
        "breakdown_by_decision_type": _decisions_by_type(decisions),
        "recommendation": build_forecast_recommendation(
            decisions=decisions,
            business_score=business_score,
            estimated_spend_reduction=estimated_spend_reduction,
            estimated_sales_lift=estimated_sales_lift,
        ),
    }


def build_forecast_recommendation(
    decisions,
    business_score,
    estimated_spend_reduction,
    estimated_sales_lift,
):
    low_risk = [d for d in decisions if d.get("risk") == "LOW"]
    high_confidence = [d for d in decisions if _safe_float(d.get("confidence")) >= 85]

    if not decisions:
        return {
            "priority": "LOW",
            "action": "No open decisions require action right now.",
            "reason": "There are no open decisions in the current forecast.",
        }

    if low_risk and high_confidence:
        return {
            "priority": "HIGH",
            "action": "Review and consider approving LOW-risk, high-confidence decisions.",
            "reason": (
                f"There are {len(low_risk)} LOW-risk decisions and "
                f"{len(high_confidence)} high-confidence decisions. "
                f"Estimated spend reduction is ${estimated_spend_reduction:.2f} and "
                f"estimated sales lift is ${estimated_sales_lift:.2f}."
            ),
        }

    return {
        "priority": "MEDIUM",
        "action": "Review open decisions manually before approval.",
        "reason": (
            f"Business score is {business_score.get('score')}. Some decisions may require manual review."
        ),
    }
