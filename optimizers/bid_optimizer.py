"""
Business OS v6.4
Complete Bid Optimizer

Adds a fuller keyword bid optimizer lifecycle:
- INCREASE_BID
- REDUCE_BID
- shared bid policy guardrails
- learning-aware confidence metadata
- placement-modifier scaffolding for the upcoming placement optimizer

This module still uses SearchTermDailyDetail as the source of truth, so it can
ship safely before placement/hourly report storage is expanded.
"""

from database import SessionLocal
from models import SearchTermDailyDetail
from ai.decisions.shared import safe_float, safe_int, sort_decisions
from business_data_context import apply_date_context, apply_marketplace_context
from intelligence_services import (
    BidPolicy,
    DecisionFactory,
    EvidenceEngine,
    ImpactEstimator,
    RiskEngine,
    ScoringEngine,
)
from optimizers.base_optimizer import BaseOptimizer
from optimizers.opportunity_queue import build_opportunity, sort_opportunities

try:
    from outcome_intelligence.learning_engine import LearningEngine
except Exception:  # pragma: no cover - keeps optimizer safe if v6.3 not installed yet
    LearningEngine = None


class BidOptimizer(BaseOptimizer):
    version = "6.1.0"
    capabilities = ["bid_scaling", "bid_reduction", "placement_modifier_scaffolding"]
    supported_objectives = ["MAXIMIZE_PROFIT", "PRESERVE_CASH", "MAXIMIZE_REVENUE"]
    risk_profile = "MEDIUM"

    name = "bid_optimizer"
    decision_types = [
        "REDUCE_BID",
        "INCREASE_BID",
        "REDUCE_PLACEMENT_MODIFIER",
        "INCREASE_PLACEMENT_MODIFIER",
    ]

    min_spend = 3
    min_clicks = 2
    min_orders_for_bid_change = 1
    max_rows = 100

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

            self.data = query.order_by(SearchTermDailyDetail.spend.desc()).limit(self.max_rows).all()

        finally:
            db.close()

    def detect(self):
        opportunities = []

        for row in self.data or []:
            spend = safe_float(row.spend)
            sales = safe_float(row.sales)
            clicks = safe_int(row.clicks)
            orders = safe_int(row.orders)

            if spend <= 0 or sales <= 0 or orders <= 0:
                continue

            acos = spend / sales
            roas = sales / spend

            recommendation = BidPolicy.recommend_keyword_change(
                acos=acos,
                roas=roas,
                orders=orders,
                clicks=clicks,
                spend=spend,
                sales=sales,
            )

            if not recommendation:
                continue

            opportunity = self._build_keyword_bid_opportunity(
                row=row,
                spend=spend,
                sales=sales,
                clicks=clicks,
                orders=orders,
                acos=acos,
                roas=roas,
                recommendation=recommendation,
            )
            if opportunity:
                opportunities.append(opportunity)

        self.opportunities = sort_opportunities(opportunities)

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

    def _learning_adjustment(self, decision_type, confidence):
        """Attach learning metadata without making the optimizer dependent on v6.3 tables."""
        learning = {
            "enabled": False,
            "confidence_before_learning": confidence,
            "confidence_after_learning": confidence,
            "message": "No learning adjustment applied.",
        }

        if LearningEngine is None:
            return confidence, learning

        try:
            summary = LearningEngine.feedback_summary()
            rows = summary.get("learning_summary", []) if isinstance(summary, dict) else []
            matching = [
                row for row in rows
                if row.get("decision_type") == decision_type and row.get("optimizer_name") in (self.name, None)
            ]
            if not matching:
                return confidence, learning

            best = matching[0]
            avg_accuracy = safe_float(best.get("avg_accuracy"))
            sample_size = safe_int(best.get("sample_size"))
            if sample_size < 3:
                learning.update({
                    "enabled": True,
                    "sample_size": sample_size,
                    "avg_accuracy": avg_accuracy,
                    "message": "Learning data found but sample size is still small.",
                })
                return confidence, learning

            if avg_accuracy >= 85:
                adjusted = min(confidence + 5, 95)
            elif avg_accuracy < 60:
                adjusted = max(confidence - 10, 40)
            else:
                adjusted = confidence

            learning.update({
                "enabled": True,
                "sample_size": sample_size,
                "avg_accuracy": avg_accuracy,
                "confidence_after_learning": adjusted,
                "message": "Confidence adjusted using historical outcome accuracy.",
            })
            return adjusted, learning
        except Exception as exc:
            learning["message"] = f"Learning adjustment skipped: {exc}"
            return confidence, learning

    def _build_keyword_bid_opportunity(self, row, spend, sales, clicks, orders, acos, roas, recommendation):
        decision_type = recommendation["action"]
        change_percent = recommendation["percent"]
        base_confidence = BidPolicy.confidence_for_keyword_change(
            action=decision_type,
            acos=acos,
            roas=roas,
            orders=orders,
            clicks=clicks,
        )
        confidence, learning_metadata = self._learning_adjustment(decision_type, base_confidence)

        if decision_type == "REDUCE_BID":
            estimated_impact = ImpactEstimator.reduce_bid(spend, change_percent)
            payload_key = "suggested_bid_reduction_percent"
            direction = "reduction"
            title = f'Reduce bid by {change_percent}% for "{row.search_term}"'
            reason = (
                f'"{row.search_term}" has ACOS {acos * 100:.1f}% '
                f"with ${spend:.2f} spend and ${sales:.2f} sales."
            )
        else:
            estimated_impact = ImpactEstimator.increase_bid(sales, change_percent, efficiency_multiplier=1.0)
            payload_key = "suggested_bid_increase_percent"
            direction = "increase"
            title = f'Increase bid by {change_percent}% for "{row.search_term}"'
            reason = (
                f'"{row.search_term}" is efficient with ACOS {acos * 100:.1f}% '
                f"and ROAS {roas:.2f}."
            )

        evidence = EvidenceEngine.search_term(row, context=self.context)
        payload = self._base_payload(row, spend, sales, clicks, orders, acos, roas)
        payload[payload_key] = change_percent
        payload[f"{direction}_percent"] = change_percent
        payload["change_percent"] = change_percent if decision_type == "INCREASE_BID" else -change_percent
        payload["bid_policy"] = recommendation
        payload["learning"] = learning_metadata
        payload["evidence"] = evidence

        risk_assessment = RiskEngine.evaluate(
            decision=decision_type,
            confidence=confidence,
            estimated_monthly_impact=estimated_impact,
            payload=payload,
        )
        payload["risk_assessment"] = risk_assessment

        opportunity = build_opportunity(
            optimizer=self.name,
            decision=decision_type,
            title=title,
            reason=f"{reason} {recommendation.get('reason')}",
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
        return opportunity

    def estimate_impact(self):
        return self.opportunities

    def assess_risk(self):
        return self.opportunities

    def build_decisions(self):
        decisions = []

        for opportunity in self.opportunities:
            payload = opportunity["payload"]
            risk_assessment = payload.get("risk_assessment", {})
            learning = payload.get("learning", {})

            reasoning = [
                f"Data window: {self.context.get('start_date')} to {self.context.get('end_date')}.",
                *EvidenceEngine.summarize(payload.get("evidence", {})),
                f"Bid policy: {payload.get('bid_policy', {}).get('reason')}",
                f"Opportunity score: {opportunity['score']}.",
                f"Risk assessment: {risk_assessment.get('overall_risk')}.",
            ]
            if learning.get("enabled"):
                reasoning.append(
                    f"Learning: {learning.get('message')} "
                    f"Accuracy={learning.get('avg_accuracy')}, sample={learning.get('sample_size')}."
                )

            decisions.append(
                DecisionFactory.create(
                    decision=opportunity["decision"],
                    priority="HIGH" if opportunity["confidence"] >= 85 else "MEDIUM",
                    confidence=opportunity["confidence"],
                    risk=opportunity["risk"],
                    estimated_monthly_impact=opportunity["estimated_monthly_impact"],
                    reasoning=reasoning,
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
