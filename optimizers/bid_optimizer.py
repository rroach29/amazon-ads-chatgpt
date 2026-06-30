"""
Business OS v6.0.0
Bid Optimizer

First pass:
- REDUCE_BID when a keyword/search term has sales but ACOS is too high.
- INCREASE_BID when a keyword/search term is efficient but likely underexposed.

This optimizer emits opportunities and decisions. Existing bid execution can be
wired to these decisions.
"""

from database import SessionLocal
from models import SearchTermDailyDetail
from ai.decisions.shared import make_decision, safe_float, safe_int, sort_decisions
from business_data_context import apply_date_context, apply_marketplace_context
from decision_risk_engine import assess_decision_risk
from optimizers.base_optimizer import BaseOptimizer
from optimizers.opportunity_queue import build_opportunity, sort_opportunities


class BidOptimizer(BaseOptimizer):
    name = "bid_optimizer"
    decision_types = ["REDUCE_BID", "INCREASE_BID"]

    min_spend = 3
    min_clicks = 2
    min_orders_for_bid_change = 1
    high_acos_threshold = 0.40
    efficient_acos_threshold = 0.25

    def collect(self):
        db = SessionLocal()

        try:
            query = (
                db.query(SearchTermDailyDetail)
                .filter(SearchTermDailyDetail.channel == "amazon_ads")
                .filter(SearchTermDailyDetail.profile_id.isnot(None))
                .filter(SearchTermDailyDetail.country_code.isnot(None))
                .filter(SearchTermDailyDetail.keyword_id.isnot(None))
                .filter(SearchTermDailyDetail.spend >= self.min_spend)
                .filter(SearchTermDailyDetail.clicks >= self.min_clicks)
                .filter(SearchTermDailyDetail.orders >= self.min_orders_for_bid_change)
                .filter(SearchTermDailyDetail.sales > 0)
            )

            query = apply_date_context(query, SearchTermDailyDetail, self.context)
            query = apply_marketplace_context(query, SearchTermDailyDetail, self.context)

            self.data = query.order_by(SearchTermDailyDetail.spend.desc()).limit(50).all()

        finally:
            db.close()

    def detect(self):
        opportunities = []

        for row in self.data or []:
            spend = safe_float(row.spend)
            sales = safe_float(row.sales)
            clicks = safe_int(row.clicks)
            orders = safe_int(row.orders)

            if spend <= 0 or sales <= 0:
                continue

            acos = spend / sales
            roas = sales / spend

            if acos >= self.high_acos_threshold:
                opportunities.append(self._build_reduce_bid_opportunity(row, spend, sales, clicks, orders, acos, roas))

            elif acos <= self.efficient_acos_threshold and orders >= 1:
                opportunities.append(self._build_increase_bid_opportunity(row, spend, sales, clicks, orders, acos, roas))

        self.opportunities = sort_opportunities([item for item in opportunities if item])

    def _base_payload(self, row, spend, sales, clicks, orders, acos, roas):
        return {
            "campaign_id": str(row.campaign_id),
            "campaign_name": row.campaign_name,
            "ad_group_id": row.ad_group_id,
            "ad_group_name": row.ad_group_name,
            "keyword_id": str(row.keyword_id),
            "keyword": row.keyword,
            "match_type": row.match_type,
            "search_term": row.search_term,
            "profile_id": row.profile_id,
            "country_code": row.country_code,
            "marketplace": row.marketplace,
            "currency": row.currency,
            "data_window": self.context,
            "spend": spend,
            "clicks": clicks,
            "sales": sales,
            "orders": orders,
            "acos": round(acos, 4),
            "roas": round(roas, 4),
        }

    def _build_reduce_bid_opportunity(self, row, spend, sales, clicks, orders, acos, roas):
        if acos >= 0.80:
            reduction_percent = 30
        elif acos >= 0.60:
            reduction_percent = 25
        else:
            reduction_percent = 20

        confidence = 70
        if clicks >= 5:
            confidence += 5
        if orders >= 1:
            confidence += 10
        if acos >= 0.60:
            confidence += 5
        confidence = min(confidence, 95)

        estimated_impact = round(spend * (reduction_percent / 100) * 30, 2)

        payload = self._base_payload(row, spend, sales, clicks, orders, acos, roas)
        payload["suggested_bid_reduction_percent"] = reduction_percent
        payload["reduction_percent"] = reduction_percent

        risk_assessment = assess_decision_risk(
            decision="REDUCE_BID",
            confidence=confidence,
            estimated_monthly_impact=estimated_impact,
            payload=payload,
        )
        payload["risk_assessment"] = risk_assessment

        return build_opportunity(
            optimizer=self.name,
            decision="REDUCE_BID",
            title=f'Reduce bid by {reduction_percent}% for "{row.search_term}"',
            reason=(
                f'"{row.search_term}" has ACOS {acos * 100:.1f}% '
                f"with ${spend:.2f} spend and ${sales:.2f} sales."
            ),
            confidence=confidence,
            risk=risk_assessment["overall_risk"],
            estimated_monthly_impact=estimated_impact,
            payload=payload,
        )

    def _build_increase_bid_opportunity(self, row, spend, sales, clicks, orders, acos, roas):
        increase_percent = 15 if acos <= 0.20 else 10

        confidence = 65
        if orders >= 2:
            confidence += 10
        if roas >= 4:
            confidence += 10
        if acos <= 0.15:
            confidence += 5
        confidence = min(confidence, 90)

        estimated_impact = round(sales * (increase_percent / 100), 2)

        payload = self._base_payload(row, spend, sales, clicks, orders, acos, roas)
        payload["suggested_bid_increase_percent"] = increase_percent
        payload["increase_percent"] = increase_percent

        risk_assessment = assess_decision_risk(
            decision="INCREASE_BID",
            confidence=confidence,
            estimated_monthly_impact=estimated_impact,
            payload=payload,
        )
        payload["risk_assessment"] = risk_assessment

        return build_opportunity(
            optimizer=self.name,
            decision="INCREASE_BID",
            title=f'Increase bid by {increase_percent}% for "{row.search_term}"',
            reason=(
                f'"{row.search_term}" is efficient with ACOS {acos * 100:.1f}% '
                f"and ROAS {roas:.2f}."
            ),
            confidence=confidence,
            risk=risk_assessment["overall_risk"],
            estimated_monthly_impact=estimated_impact,
            payload=payload,
        )

    def estimate_impact(self):
        return self.opportunities

    def assess_risk(self):
        return self.opportunities

    def build_decisions(self):
        decisions = []

        for opportunity in self.opportunities:
            payload = opportunity["payload"]
            risk_assessment = payload.get("risk_assessment", {})

            decisions.append(
                make_decision(
                    decision=opportunity["decision"],
                    priority="HIGH" if opportunity["confidence"] >= 85 else "MEDIUM",
                    confidence=opportunity["confidence"],
                    risk=opportunity["risk"],
                    estimated_monthly_impact=opportunity["estimated_monthly_impact"],
                    reasoning=[
                        f"Data window: {self.context.get('start_date')} to {self.context.get('end_date')}.",
                        opportunity["reason"],
                        f"Opportunity score: {opportunity['score']}.",
                        f"Risk assessment: {risk_assessment.get('overall_risk')}.",
                    ],
                    recommended_action=opportunity["title"],
                    payload=payload,
                )
            )

        self.decisions = sort_decisions(decisions)
