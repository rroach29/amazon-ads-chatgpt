"""
Business OS v8.2
Optimizer Domain Model Compatibility Layer

The canonical typed models now live in domain/. This file preserves existing
optimizer imports while routing to the shared domain contracts.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from domain import Evidence, ImpactEstimate, Opportunity as DomainOpportunity, RiskAssessment

JsonDict = Dict[str, Any]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RiskProfile(RiskAssessment):
    """Backward-compatible alias for the former optimizer RiskProfile."""

    @classmethod
    def from_dict(cls, value: Optional[JsonDict]) -> "RiskProfile":
        value = value or {}
        raw = {
            "overall_risk": value.get("overall_risk") or value.get("risk") or "MEDIUM",
            "technical_risk": value.get("technical_risk") or "LOW",
            "financial_risk": value.get("financial_risk") or "MEDIUM",
            "operational_risk": value.get("operational_risk") or "LOW",
            "reversibility": value.get("reversibility") or "MEDIUM",
            "factors": value.get("factors") if isinstance(value.get("factors"), list) else [],
        }
        return cls(**raw)


@dataclass
class Opportunity:
    """Backward-compatible wrapper returning the legacy opportunity dictionary."""

    optimizer: str
    decision: str
    title: str
    reason: str
    confidence: float
    risk: str
    estimated_monthly_impact: float
    score: float
    payload: JsonDict = field(default_factory=dict)
    evidence: List[Evidence] = field(default_factory=list)
    impact: Optional[ImpactEstimate] = None
    risk_assessment: Optional[RiskProfile] = None
    created_at: str = field(default_factory=_utc_now_iso)
    schema_version: str = "8.2"

    def to_dict(self) -> JsonDict:
        model = DomainOpportunity(
            optimizer_name=self.optimizer,
            optimizer_version=self.payload.get("optimizer_version") if isinstance(self.payload, dict) else None,
            decision=self.decision,
            title=self.title,
            reason=self.reason,
            confidence=self.confidence,
            risk=str(self.risk or "MEDIUM").upper(),
            estimated_monthly_impact=self.estimated_monthly_impact,
            score=self.score,
            payload=self.payload or {},
            evidence=self.evidence or [],
            impact=self.impact,
            risk_assessment=self.risk_assessment,
            created_at=self.created_at,
        )
        result = model.to_dict()
        # Preserve keys expected by older optimizer/plan code.
        result["optimizer"] = result.get("optimizer_name", self.optimizer)
        result["schema_version"] = self.schema_version
        return result


@dataclass
class OptimizerRunMetrics:
    optimizer: str
    opportunity_count: int = 0
    decision_count: int = 0
    status: str = "OK"
    runtime_ms: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> JsonDict:
        return asdict(self)
