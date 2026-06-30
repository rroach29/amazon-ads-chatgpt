"""
Business OS v6.1.0
Bid Optimizer

Detects both REDUCE_BID and INCREASE_BID opportunities using the shared
optimizer platform models, scoring, configuration, and evidence layer.
"""

from database import SessionLocal
from models import SearchTermDailyDetail
from ai.decisions.shared import make_decision, safe_float, safe_int, sort_decisions
from business_data_context import apply_date_context, apply_marketplace_context
from decision_risk_engine import assess_decision_risk
from optimizers.base_optimizer import BaseOptimizer
from optimizers.config import BidOptimizerConfig
from optimizers.domain_models import Evidence, ImpactEstimate
from optimizers.opportunity_queue import build_opportunity, sort_opportunities
from optimizers.scoring import priority_from_confidence


class BidOptimizer(BaseOptimizer):
    name = "bid_optimizer"
    version = "6.1.0"
    decision_types = ["REDUCE_BID", "INCREASE_BID"]

    def __init__(self, context=None, config=None):
        super().__init__(context=context)
        self.config = config or BidOptimizerConfig()

    def collect(self):
        db = SessionLocal()

        try:
            query = (
                db.query(SearchTermDailyDetail)
                .filter(SearchTermDailyDetail.channel == "amazon_ads")
                .filter(SearchTermDailyDetail.profile_id.isnot(None))
                .filter(SearchTermDailyDetail.country_code.isnot(None))
                .filter(SearchTermDailyDetail.keyword_id.isnot(None))
                .filter(SearchTermDailyDetail.spend >= self.config.min_spend)
                .filter(SearchTermDailyDetail.clicks >= self.config.min_clicks)
                .filter(SearchTermDailyDetail.orders >= self.config.min_orders_for_bid_change)
                .filter(SearchTermDailyDetail.sales > 0)
            )

            query = apply_date_context(query, SearchTermDailyDetail, self.context)
            query = apply_marketplace_context(query, SearchTermDailyDetail, self.context)

            self.data = query.order_by(SearchTermDailyDetail.spend.desc()).limit(self.config.max_rows).all()

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

            if acos >= self.config.high_acos_threshold:
                opportunities.append(self._build_reduce_bid_opportunity(row, spend, sales, clicks, orders, acos, roas))
            elif acos <= self.config.efficient_acos_threshold and orders >= 1:
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
            "optimizer_version": self.version,
        }

    def _evidence(self, row, spend, sales, clicks, orders, acos, roas):
        return [
            Evidence(
                source="SearchTermDailyDetail",
                metric="acos",
                value=round(acos, 4),
                description=f"ACOS {acos * 100:.1f}% on ${spend:.2f} spend and ${sales:.2f} sales.",
                weight=1.0,
            ),
            Evidence(
                source="SearchTermDailyDetail",
                metric="roas",
                value=round(roas, 4),
                description=f"ROAS {roas:.2f} with {orders} orders from {clicks} clicks.",
                weight=0.9,
            ),
        ]

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
            evidence=self._evidence(row, spend, sales, clicks, orders, acos, roas),
            impact=ImpactEstimate(
                estimated_monthly_impact=estimated_impact,
                currency=row.currency,
                basis=f"daily_spend_x_{reduction_percent}_percent_x_30",
                confidence=confidence,
            ),
            risk_assessment=risk_assessment,
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
            evidence=self._evidence(row, spend, sales, clicks, orders, acos, roas),
            impact=ImpactEstimate(
                estimated_monthly_impact=estimated_impact,
                currency=row.currency,
                basis=f"sales_x_{increase_percent}_percent_incremental_opportunity",
                confidence=confidence,
            ),
            risk_assessment=risk_assessment,
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
                    priority=priority_from_confidence(opportunity["confidence"], opportunity["risk"]),
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
