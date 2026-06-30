"""Business OS v8.6 — Revenue Intelligence domain helpers.

Revenue Intelligence reconciles Seller Central total revenue with Amazon Ads
paid attributed revenue. The Seller Central side is represented by the
seller_central_sales_traffic table, which can be populated later from SP-API
GET_SALES_AND_TRAFFIC_REPORT or manual imports.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class RevenueBreakdown:
    total_revenue: float
    paid_revenue: float
    organic_revenue: float
    ad_spend: float
    orders: int = 0
    units_ordered: int = 0
    sessions: int = 0
    currency: str | None = None
    confidence: int = 0
    basis: str = "estimated"

    def to_dict(self) -> dict[str, Any]:
        total = self.total_revenue or 0.0
        paid_ratio = self.paid_revenue / total if total else None
        organic_ratio = self.organic_revenue / total if total else None
        tacos = self.ad_spend / total if total else None
        conversion_rate = self.units_ordered / self.sessions if self.sessions else None
        return {
            **asdict(self),
            "total_revenue": round(self.total_revenue, 2),
            "paid_revenue": round(self.paid_revenue, 2),
            "organic_revenue": round(self.organic_revenue, 2),
            "ad_spend": round(self.ad_spend, 2),
            "paid_ratio": round(paid_ratio, 4) if paid_ratio is not None else None,
            "organic_ratio": round(organic_ratio, 4) if organic_ratio is not None else None,
            "tacos": round(tacos, 4) if tacos is not None else None,
            "conversion_rate": round(conversion_rate, 4) if conversion_rate is not None else None,
            "advertising_dependency": RevenueSignals.advertising_dependency(paid_ratio),
            "organic_momentum": RevenueSignals.organic_momentum(organic_ratio),
        }


class RevenueSignals:
    @staticmethod
    def advertising_dependency(paid_ratio: float | None) -> str:
        if paid_ratio is None:
            return "UNKNOWN"
        if paid_ratio >= 0.70:
            return "HIGH"
        if paid_ratio >= 0.40:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def organic_momentum(organic_ratio: float | None) -> str:
        if organic_ratio is None:
            return "UNKNOWN"
        if organic_ratio >= 0.65:
            return "STRONG"
        if organic_ratio >= 0.40:
            return "BALANCED"
        return "WEAK"

    @staticmethod
    def recommendation(item: dict[str, Any]) -> dict[str, str]:
        dep = item.get("advertising_dependency")
        organic = item.get("organic_momentum")
        total = float(item.get("total_revenue") or 0)
        paid = float(item.get("paid_revenue") or 0)
        spend = float(item.get("ad_spend") or 0)
        if total <= 0 and spend > 0:
            return {"signal": "AD_SPEND_WITHOUT_REVENUE", "message": "Ad spend exists but Seller Central revenue is unavailable or zero for this window."}
        if dep == "HIGH":
            return {"signal": "AD_DEPENDENT", "message": "Revenue is highly dependent on paid advertising. Improve listing conversion and organic rank before aggressive scaling."}
        if organic == "STRONG" and paid > 0:
            return {"signal": "ORGANIC_MOMENTUM", "message": "Organic revenue is strong relative to paid revenue. Consider scaling ads carefully if profit supports it."}
        if dep == "LOW" and total > 0:
            return {"signal": "ORGANIC_STRENGTH", "message": "Product or marketplace appears less dependent on advertising. Protect organic strength while testing profitable growth."}
        return {"signal": "MONITOR", "message": "Revenue mix is balanced or still developing. Monitor organic and paid trends before major changes."}
