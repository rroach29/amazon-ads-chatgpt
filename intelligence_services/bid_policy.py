"""
Business OS v6.4
Bid Policy Service

Centralizes bid-change guardrails and recommendations so bid optimizer and
execution adapter use consistent business rules.
"""


def _safe_float(value, default=0.0):
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


class BidPolicy:
    MIN_BID = 0.02
    MAX_BID = 10.00
    MAX_INCREASE_PERCENT = 25
    MAX_DECREASE_PERCENT = 50

    @classmethod
    def recommend_keyword_change(cls, acos, roas, orders=0, clicks=0, spend=0, sales=0):
        """Return a conservative keyword-level bid change recommendation."""
        acos = _safe_float(acos)
        roas = _safe_float(roas)
        orders = int(_safe_float(orders))
        clicks = int(_safe_float(clicks))
        spend = _safe_float(spend)
        sales = _safe_float(sales)

        if spend <= 0 or sales <= 0 or orders <= 0:
            return None

        if acos >= 0.80:
            return {"action": "REDUCE_BID", "percent": 30, "reason": "ACOS is severely above target."}
        if acos >= 0.60:
            return {"action": "REDUCE_BID", "percent": 25, "reason": "ACOS is materially above target."}
        if acos >= 0.40:
            return {"action": "REDUCE_BID", "percent": 20, "reason": "ACOS is above target."}

        if acos <= 0.15 and roas >= 5 and orders >= 1:
            return {"action": "INCREASE_BID", "percent": 20, "reason": "Search term is very efficient and can likely scale."}
        if acos <= 0.25 and roas >= 4 and orders >= 1:
            return {"action": "INCREASE_BID", "percent": 15, "reason": "Search term is efficient and can likely scale."}
        if acos <= 0.30 and roas >= 3 and orders >= 2:
            return {"action": "INCREASE_BID", "percent": 10, "reason": "Search term has repeat conversion evidence."}

        return None

    @classmethod
    def recommend_placement_change(cls, placement, spend, sales, orders, acos, roas):
        """Return a placement modifier recommendation placeholder.

        The current report model may not expose placement rows everywhere, so this
        method is intentionally isolated. Once placement/hourly reports are stored,
        the optimizer can call this without changing scoring or execution layers.
        """
        placement = (placement or "").lower()
        if not placement:
            return None

        if acos and acos <= 0.20 and roas >= 4 and orders >= 1:
            return {
                "action": "INCREASE_PLACEMENT_MODIFIER",
                "percent": 10,
                "reason": f"{placement} placement is efficient and may deserve more exposure.",
            }
        if acos and acos >= 0.60 and spend > 0:
            return {
                "action": "REDUCE_PLACEMENT_MODIFIER",
                "percent": 10,
                "reason": f"{placement} placement is inefficient and should be constrained.",
            }
        return None

    @classmethod
    def clamp_new_bid(cls, current_bid, change_percent):
        current_bid = _safe_float(current_bid)
        change_percent = _safe_float(change_percent)
        new_bid = current_bid * (1 + change_percent / 100)
        return round(min(max(new_bid, cls.MIN_BID), cls.MAX_BID), 2)

    @classmethod
    def confidence_for_keyword_change(cls, action, acos, roas, orders=0, clicks=0):
        action = (action or "").upper()
        acos = _safe_float(acos)
        roas = _safe_float(roas)
        orders = int(_safe_float(orders))
        clicks = int(_safe_float(clicks))

        confidence = 65
        if clicks >= 5:
            confidence += 5
        if orders >= 2:
            confidence += 10
        elif orders >= 1:
            confidence += 5

        if action == "REDUCE_BID" and acos >= 0.60:
            confidence += 10
        if action == "INCREASE_BID" and roas >= 4:
            confidence += 10
        if action == "INCREASE_BID" and acos <= 0.15:
            confidence += 5

        return min(confidence, 95)
