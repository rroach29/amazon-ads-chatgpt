"""
Business OS v6.2
Keyword Optimizer

Uses shared intelligence services for impact, risk, evidence, scoring, and
standardized decision creation.
"""

from database import SessionLocal
from models import SearchTermDailyDetail
from ai.decisions.shared import safe_float, safe_int, sort_decisions
from business_data_context import apply_date_context, apply_marketplace_context
from intelligence_services import (
    DecisionFactory,
    EvidenceEngine,
    ImpactEstimator,
    RiskEngine,
    ScoringEngine,
)
from optimizers.base_optimizer import BaseOptimizer
from optimizers.opportunity_queue import build_opportunity, sort_opportunities


class KeywordOptimizer(BaseOptimizer):
    version = "6.1.0"
    capabilities = ["keyword_waste_detection", "negative_keyword_recommendations"]
    supported_objectives = ["MAXIMIZE_PROFIT", "PRESERVE_CASH", "MAXIMIZE_REVENUE"]
    risk_profile = "LOW"

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

            estimated_impact = ImpactEstimator.negative_keyword(spend)
            evidence = EvidenceEngine.search_term(row, context=self.context)

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
                "evidence": evidence,
            }

            risk_assessment = RiskEngine.evaluate(
                decision="ADD_NEGATIVE_KEYWORD",
                confidence=confidence,
                estimated_monthly_impact=estimated_impact,
                payload=payload,
            )
            payload["risk_assessment"] = risk_assessment

            opportunity = build_opportunity(
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
            opportunity["score"] = ScoringEngine.opportunity_score(
                confidence=confidence,
                estimated_monthly_impact=estimated_impact,
                risk=risk_assessment["overall_risk"],
            )
            opportunity["evidence"] = evidence
            opportunities.append(opportunity)

        self.opportunities = sort_opportunities(opportunities)

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
                DecisionFactory.create(
                    decision="ADD_NEGATIVE_KEYWORD",
                    priority="HIGH" if opportunity["confidence"] >= 85 else "MEDIUM",
                    confidence=opportunity["confidence"],
                    risk=opportunity["risk"],
                    estimated_monthly_impact=opportunity["estimated_monthly_impact"],
                    reasoning=[
                        f"Data window: {self.context.get('start_date')} to {self.context.get('end_date')}.",
                        *EvidenceEngine.summarize(payload.get("evidence", {})),
                        "Negative keyword action is reversible and does not increase spend.",
                        f"Opportunity score: {opportunity['score']}.",
                        f"Risk assessment: {risk_assessment.get('overall_risk')}.",
                    ],
                    recommended_action=opportunity["title"],
                    payload=payload,
                    evidence=payload.get("evidence"),
                    optimizer_name=self.name,
                    optimizer_version=self.version,
                    optimizer_class=self.__class__.__name__,
                    source_opportunity_id=opportunity.get("opportunity_id"),
                    opportunity=opportunity,
                    data_context=self.context,
                )
            )

        self.decisions = sort_decisions(decisions)
