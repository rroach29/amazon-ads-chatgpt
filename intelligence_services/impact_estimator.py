"""
Business OS v6.4
Impact Estimator

Centralizes rough business impact estimates so optimizers do not invent their
own formulas. These are conservative estimates intended for decision ranking,
not accounting-grade forecasts.
"""


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


class ImpactEstimator:
    @staticmethod
    def negative_keyword(spend, lookback_days=1):
        spend = _safe_float(spend)
        days = max(int(lookback_days or 1), 1)
        return round((spend / days) * 30, 2)

    @staticmethod
    def reduce_bid(spend, reduction_percent, lookback_days=1):
        spend = _safe_float(spend)
        days = max(int(lookback_days or 1), 1)
        pct = max(_safe_float(reduction_percent), 0) / 100
        return round((spend / days) * pct * 30, 2)

    @staticmethod
    def increase_bid(sales, increase_percent, efficiency_multiplier=1.0, lookback_days=1):
        sales = _safe_float(sales)
        days = max(int(lookback_days or 1), 1)
        pct = max(_safe_float(increase_percent), 0) / 100
        multiplier = max(_safe_float(efficiency_multiplier, 1.0), 0)
        return round((sales / days) * pct * multiplier * 30, 2)

    @staticmethod
    def placement_modifier(value, modifier_percent, lookback_days=1):
        value = _safe_float(value)
        days = max(int(lookback_days or 1), 1)
        pct = max(_safe_float(modifier_percent), 0) / 100
        return round((value / days) * pct * 30, 2)

    @staticmethod
    def budget_change(lost_sales_or_sales, change_percent):
        value = _safe_float(lost_sales_or_sales)
        pct = max(_safe_float(change_percent), 0) / 100
        return round(value * pct, 2)
