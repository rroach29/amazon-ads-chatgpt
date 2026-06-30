"""
Business OS v6.0.0
Keyword Optimizer

First optimizer converted into the new framework.
Currently detects negative keyword opportunities from current-window search terms.
"""

from database import SessionLocal
from models import SearchTermDailyDetail
from ai.decisions.shared import make_decision, safe_float, safe_int, sort_decisions
from business_data_context import apply_date_context, apply_marketplace_context
from decision_risk_engine import assess_decision_risk
from optimizers.base_optimizer import BaseOptimizer
from optimizers.opportunity_queue import build_opportunity, sort_opportunities


class KeywordOptimizer(BaseOptimizer):
    name = "keyword_optimizer"
    decision_types = ["ADD_NEGATIVE_KEYWORD"]

    min_spend = 3
    min_clicks = 2

    def collect(self):
        db = SessionLocal()

        try:
            query = (
                db.query(SearchTermDailyDetail)
                .filter(SearchTermDailyDetail.channel == "amazon_ads")
                .filter(SearchTermDailyDetail.profile_id.isnot(None))
                .filter(SearchTermDailyDetail.country_code.isnot(None))
                .filter(SearchTermDailyDetail.spend >= self.min_spend)
                .filter(SearchTermDailyDetail.clicks >= self.min_clicks)
                .filter(SearchTermDailyDetail.sales == 0)
            )

            query = apply_date_context(query, SearchTermDailyDetail, self.context)
            query = apply_marketplace_context(query, SearchTermDailyDetail, self.context)

            self.data = query.order_by(SearchTermDailyDetail.spend.desc()).limit(25).all()

        finally:
            db.close()

    def detect(self):
        opportunities = []

        for row in self.data or []:
            spend = safe_float(row.spend)
            clicks = safe_int(row.clicks)

            confidence = 70
            if clicks >= 5:
                confidence += 10
            if spend >= 10:
                confidence += 10
            if spend >= 20:
                confidence += 9

            confidence = min(confidence, 99)
            estimated_impact = round(spend * 30, 2)

            payload = {
                "campaign_id": str(row.campaign_id),
                "campaign_name": row.campaign_name,
                "ad_group_id": row.ad_group_id,
                "ad_group_name": row.ad_group_name,
                "keyword_id": str(row.keyword_id) if row.keyword_id else None,
                "keyword": row.keyword,
                "match_type": row.match_type,
                "search_term": row.search_term,
                "negative_match_type": "phrase",
                "profile_id": row.profile_id,
                "country_code": row.country_code,
                "marketplace": row.marketplace,
                "currency": row.currency,
                "data_window": self.context,
                "spend": spend,
                "clicks": clicks,
                "sales": safe_float(row.sales),
                "orders": safe_int(row.orders),
                "acos": row.acos,
                "roas": row.roas,
            }

            risk_assessment = assess_decision_risk(
                decision="ADD_NEGATIVE_KEYWORD",
                confidence=confidence,
                estimated_monthly_impact=estimated_impact,
                payload=payload,
            )

            payload["risk_assessment"] = risk_assessment

            opportunities.append(
                build_opportunity(
                    optimizer=self.name,
                    decision="ADD_NEGATIVE_KEYWORD",
                    title=f"Add negative phrase: {row.search_term}",
                    reason=(
                        f'"{row.search_term}" spent ${spend:.2f} '
                        f"with {clicks} clicks and no sales."
                    ),
                    confidence=confidence,
                    risk=risk_assessment["overall_risk"],
                    estimated_monthly_impact=estimated_impact,
                    payload=payload,
                )
            )

        self.opportunities = sort_opportunities(opportunities)

    def estimate_impact(self):
        # Impact is already estimated in detect for v6.0.
        return self.opportunities

    def assess_risk(self):
        # Risk is already assessed in detect for v6.0.
        return self.opportunities

    def build_decisions(self):
        decisions = []

        for opportunity in self.opportunities:
            payload = opportunity["payload"]
            risk_assessment = payload.get("risk_assessment", {})

            decisions.append(
                make_decision(
                    decision="ADD_NEGATIVE_KEYWORD",
                    priority="HIGH" if opportunity["confidence"] >= 85 else "MEDIUM",
                    confidence=opportunity["confidence"],
                    risk=opportunity["risk"],
                    estimated_monthly_impact=opportunity["estimated_monthly_impact"],
                    reasoning=[
                        f"Data window: {self.context.get('start_date')} to {self.context.get('end_date')}.",
                        opportunity["reason"],
                        "Negative keyword action is reversible and does not increase spend.",
                        f"Opportunity score: {opportunity['score']}.",
                        f"Risk assessment: {risk_assessment.get('overall_risk')}.",
                    ],
                    recommended_action=opportunity["title"],
                    payload=payload,
                )
            )

        self.decisions = sort_decisions(decisions)
