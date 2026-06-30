"""
Business OS v7.1
Budget Optimizer

Adds campaign-level budget intelligence using the existing CampaignDailyDetail
reporting table and the shared intelligence services introduced in v6.2+.

Decision types:
- INCREASE_BUDGET
- DECREASE_BUDGET

This optimizer is intentionally conservative. It produces executable/simulated
budget decisions without requiring a new SQL migration or a live budget API.
"""

from database import SessionLocal
from models import CampaignDailyDetail
from ai.decisions.shared import safe_float, safe_int, sort_decisions
from business_data_context import apply_date_context, apply_marketplace_context
from intelligence_services import (
    BudgetPolicy,
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
except Exception:  # pragma: no cover
    LearningEngine = None


class BudgetOptimizer(BaseOptimizer):
    name = "budget_optimizer"
    version = "7.1.0"
    decision_types = ["INCREASE_BUDGET", "DECREASE_BUDGET"]

    min_spend = 5
    min_clicks = 2
    max_rows = 100

    def collect(self):
        db = SessionLocal()
        try:
            query = (
                db.query(CampaignDailyDetail)
                .filter(CampaignDailyDetail.channel == "amazon_ads")
                .filter(CampaignDailyDetail.profile_id.isnot(None))
                .filter(CampaignDailyDetail.country_code.isnot(None))
                .filter(CampaignDailyDetail.spend >= self.min_spend)
                .filter(CampaignDailyDetail.clicks >= self.min_clicks)
            )
            query = apply_date_context(query, CampaignDailyDetail, self.context)
            query = apply_marketplace_context(query, CampaignDailyDetail, self.context)
            self.data = query.order_by(CampaignDailyDetail.spend.desc()).limit(self.max_rows).all()
        finally:
            db.close()

    def detect(self):
        opportunities = []
        for row in self.data or []:
            spend = safe_float(row.spend)
            sales = safe_float(row.sales)
            clicks = safe_int(row.clicks)
            orders = safe_int(row.orders)
            impressions = safe_int(row.impressions)

            recommendation = BudgetPolicy.recommend_campaign_budget_change(
                spend=spend,
                sales=sales,
                orders=orders,
                clicks=clicks,
                impressions=impressions,
                campaign_name=row.campaign_name,
            )
            if not recommendation:
                continue

            opportunity = self._build_budget_opportunity(
                row=row,
                spend=spend,
                sales=sales,
                clicks=clicks,
                orders=orders,
                impressions=impressions,
                recommendation=recommendation,
            )
            if opportunity:
                opportunities.append(opportunity)

        self.opportunities = sort_opportunities(opportunities)

    def _learning_adjustment(self, decision_type, confidence):
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
            matching = [row for row in rows if row.get("decision_type") == decision_type]
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
            adjusted = confidence
            if avg_accuracy >= 85:
                adjusted = min(confidence + 5, 95)
            elif avg_accuracy < 60:
                adjusted = max(confidence - 10, 40)
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

    def _campaign_evidence(self, row, spend, sales, clicks, orders, impressions, recommendation):
        acos = spend / sales if sales else None
        roas = sales / spend if spend else 0
        ctr = clicks / impressions if impressions else 0
        conversion_rate = orders / clicks if clicks else 0
        return {
            "type": "CAMPAIGN_BUDGET_PERFORMANCE",
            "source": "CampaignDailyDetail",
            "data_window": self.context,
            "campaign_id": str(row.campaign_id or ""),
            "campaign_name": row.campaign_name,
            "profile_id": row.profile_id,
            "country_code": row.country_code,
            "marketplace": row.marketplace,
            "currency": row.currency,
            "policy": recommendation,
            "metrics": {
                "spend": round(spend, 2),
                "sales": round(sales, 2),
                "clicks": clicks,
                "orders": orders,
                "impressions": impressions,
                "acos": round(acos, 4) if acos is not None else None,
                "roas": round(roas, 4),
                "ctr": round(ctr, 4),
                "conversion_rate": round(conversion_rate, 4),
            },
        }

    def _base_payload(self, row, spend, sales, clicks, orders, impressions, recommendation, evidence):
        metrics = evidence.get("metrics", {})
        return {
            "campaign_id": str(row.campaign_id or ""),
            "campaign_name": row.campaign_name,
            "campaign_status": getattr(row, "campaign_status", None),
            "profile_id": row.profile_id,
            "country_code": row.country_code,
            "marketplace": row.marketplace,
            "currency": row.currency,
            "data_window": self.context,
            "spend": spend,
            "sales": sales,
            "clicks": clicks,
            "orders": orders,
            "impressions": impressions,
            "acos": metrics.get("acos"),
            "roas": metrics.get("roas"),
            "budget_policy": recommendation,
            "evidence": evidence,
        }

    def _build_budget_opportunity(self, row, spend, sales, clicks, orders, impressions, recommendation):
        decision_type = recommendation["action"]
        change_percent = recommendation["percent"]
        base_confidence = BudgetPolicy.confidence_for_budget_change(
            action=decision_type,
            spend=spend,
            sales=sales,
            orders=orders,
            clicks=clicks,
        )
        confidence, learning_metadata = self._learning_adjustment(decision_type, base_confidence)
        evidence = self._campaign_evidence(row, spend, sales, clicks, orders, impressions, recommendation)
        payload = self._base_payload(row, spend, sales, clicks, orders, impressions, recommendation, evidence)
        payload["change_percent"] = change_percent if decision_type == "INCREASE_BUDGET" else -change_percent
        payload["learning"] = learning_metadata

        if decision_type == "INCREASE_BUDGET":
            estimated_impact = ImpactEstimator.budget_change(sales, change_percent)
            payload["suggested_budget_increase_percent"] = change_percent
            title = f"Increase budget by {change_percent}% for {row.campaign_name}"
            reason = recommendation.get("reason")
        else:
            estimated_impact = ImpactEstimator.budget_change(spend, change_percent)
            payload["suggested_budget_decrease_percent"] = change_percent
            title = f"Decrease budget by {change_percent}% for {row.campaign_name}"
            reason = recommendation.get("reason")

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
            reason=reason,
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
            evidence = payload.get("evidence", {})
            metrics = evidence.get("metrics", {})
            learning = payload.get("learning", {})

            reasoning = [
                f"Data window: {self.context.get('start_date')} to {self.context.get('end_date')}.",
                f"Campaign {payload.get('campaign_name')} spent ${metrics.get('spend', 0):.2f} and generated ${metrics.get('sales', 0):.2f} sales.",
                f"Orders: {metrics.get('orders', 0)}, clicks: {metrics.get('clicks', 0)}, ROAS: {metrics.get('roas', 0)}.",
                f"Budget policy: {payload.get('budget_policy', {}).get('reason')}",
                f"Opportunity score: {opportunity['score']}.",
                f"Risk assessment: {risk_assessment.get('overall_risk')}.",
            ]
            if learning.get("enabled"):
                reasoning.append(
                    f"Learning: {learning.get('message')} Accuracy={learning.get('avg_accuracy')}, sample={learning.get('sample_size')}."
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
                    evidence=evidence,
                )
            )

        self.decisions = sort_decisions(decisions)
