"""
Business OS v6.1.0
Opportunity Queue

All optimizers emit standardized opportunities. This module preserves the
existing dict API while internally supporting typed opportunity objects.
"""

from optimizers.domain_models import Evidence, ImpactEstimate, Opportunity, RiskProfile
from optimizers.scoring import opportunity_score, safe_float


def build_opportunity(
    optimizer,
    decision,
    title,
    reason,
    confidence,
    risk,
    estimated_monthly_impact,
    payload=None,
    evidence=None,
    impact=None,
    risk_assessment=None,
):
    payload = payload if isinstance(payload, dict) else {}
    evidence = evidence if isinstance(evidence, list) else []

    normalized_evidence = []
    for item in evidence:
        if isinstance(item, Evidence):
            normalized_evidence.append(item)
        elif isinstance(item, dict):
            normalized_evidence.append(Evidence(**item))

    risk_profile = None
    if isinstance(risk_assessment, RiskProfile):
        risk_profile = risk_assessment
    elif isinstance(risk_assessment, dict):
        risk_profile = RiskProfile.from_dict(risk_assessment)
    elif isinstance(payload.get("risk_assessment"), dict):
        risk_profile = RiskProfile.from_dict(payload.get("risk_assessment"))

    impact_estimate = None
    if isinstance(impact, ImpactEstimate):
        impact_estimate = impact
    elif isinstance(impact, dict):
        impact_estimate = ImpactEstimate(**impact)

    opportunity = Opportunity(
        optimizer=optimizer,
        decision=decision,
        title=title,
        reason=reason,
        confidence=confidence,
        risk=risk,
        estimated_monthly_impact=estimated_monthly_impact,
        score=opportunity_score(
            confidence=confidence,
            impact=estimated_monthly_impact,
            risk=risk,
        ),
        payload=payload,
        evidence=normalized_evidence,
        impact=impact_estimate,
        risk_assessment=risk_profile,
    )

    return opportunity.to_dict()


def sort_opportunities(opportunities):
    return sorted(
        opportunities or [],
        key=lambda item: (
            safe_float(item.get("score")),
            safe_float(item.get("estimated_monthly_impact")),
            safe_float(item.get("confidence")),
        ),
        reverse=True,
    )
