"""
Business OS v7.1
Budget Policy

Shared rules for campaign budget intelligence. This policy intentionally uses
conservative thresholds and works with the reporting tables already available
in the Business OS. It does not require hourly reports or Amazon live budget
lookups, so it is safe to deploy before deeper budget APIs are added.
"""


def _safe_float(value, default=0.0):
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default=0):
    try:
        return int(value if value is not None else default)
    except (TypeError, ValueError):
        return default


class BudgetPolicy:
    """Conservative campaign-level budget recommendations."""

    min_spend_for_budget_decision = 5.0
    min_orders_for_increase = 1
    max_good_acos = 0.35
    min_good_roas = 2.5
    poor_acos = 1.0
    poor_roas = 1.0

    @staticmethod
    def recommend_campaign_budget_change(spend, sales, orders, clicks, impressions, campaign_name=None):
        spend = _safe_float(spend)
        sales = _safe_float(sales)
        orders = _safe_int(orders)
        clicks = _safe_int(clicks)
        impressions = _safe_int(impressions)

        if spend < BudgetPolicy.min_spend_for_budget_decision:
            return None

        acos = spend / sales if sales > 0 else None
        roas = sales / spend if spend > 0 else 0
        ctr = clicks / impressions if impressions > 0 else 0
        conversion_rate = orders / clicks if clicks > 0 else 0

        # Increase budget only when there is real conversion evidence.
        if orders >= BudgetPolicy.min_orders_for_increase and sales > 0:
            if (acos is not None and acos <= BudgetPolicy.max_good_acos) or roas >= BudgetPolicy.min_good_roas:
                percent = 20 if roas >= 4 or (acos is not None and acos <= 0.25) else 10
                return {
                    "action": "INCREASE_BUDGET",
                    "percent": percent,
                    "reason": (
                        f"Campaign is efficient with ROAS {roas:.2f}"
                        + (f" and ACOS {acos * 100:.1f}%." if acos is not None else ".")
                    ),
                    "metrics": {
                        "acos": round(acos, 4) if acos is not None else None,
                        "roas": round(roas, 4),
                        "ctr": round(ctr, 4),
                        "conversion_rate": round(conversion_rate, 4),
                    },
                }

        # Decrease budget if spend is meaningful and sales are weak.
        if sales <= 0 and clicks >= 3:
            return {
                "action": "DECREASE_BUDGET",
                "percent": 15,
                "reason": f"Campaign spent ${spend:.2f} with {clicks} clicks and no attributed sales.",
                "metrics": {
                    "acos": None,
                    "roas": 0,
                    "ctr": round(ctr, 4),
                    "conversion_rate": 0,
                },
            }

        if sales > 0 and ((acos is not None and acos >= BudgetPolicy.poor_acos) or roas <= BudgetPolicy.poor_roas):
            return {
                "action": "DECREASE_BUDGET",
                "percent": 10,
                "reason": (
                    f"Campaign has weak efficiency with ROAS {roas:.2f}"
                    + (f" and ACOS {acos * 100:.1f}%." if acos is not None else ".")
                ),
                "metrics": {
                    "acos": round(acos, 4) if acos is not None else None,
                    "roas": round(roas, 4),
                    "ctr": round(ctr, 4),
                    "conversion_rate": round(conversion_rate, 4),
                },
            }

        return None

    @staticmethod
    def confidence_for_budget_change(action, spend, sales, orders, clicks):
        spend = _safe_float(spend)
        sales = _safe_float(sales)
        orders = _safe_int(orders)
        clicks = _safe_int(clicks)
        roas = sales / spend if spend > 0 else 0

        confidence = 65
        if action == "INCREASE_BUDGET":
            confidence += 8 if orders >= 1 else 0
            confidence += 7 if orders >= 2 else 0
            confidence += 8 if roas >= 3 else 0
            confidence += 5 if roas >= 5 else 0
        elif action == "DECREASE_BUDGET":
            confidence += 8 if clicks >= 3 else 0
            confidence += 7 if sales <= 0 else 0
            confidence += 5 if roas < 1 else 0

        return max(40, min(92, confidence))
