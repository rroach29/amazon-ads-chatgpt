"""
Business OS v6.1.0
Typed Optimization Domain Models

These models keep the optimizer platform extensible while preserving backward
compatibility with the existing dict-shaped API responses.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


JsonDict = Dict[str, Any]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Evidence:
    """A compact proof point that supports an optimization opportunity."""

    source: str
    metric: str
    value: Any
    description: str = ""
    weight: float = 1.0

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass
class ImpactEstimate:
    """Estimated business impact for a proposed action."""

    estimated_monthly_impact: float = 0.0
    currency: Optional[str] = None
    basis: str = "heuristic"
    confidence: Optional[float] = None

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass
class RiskProfile:
    """Structured risk profile for an optimization opportunity."""

    overall_risk: str = "MEDIUM"
    technical_risk: str = "LOW"
    financial_risk: str = "MEDIUM"
    operational_risk: str = "LOW"
    reversibility: str = "MEDIUM"
    factors: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: Optional[JsonDict]) -> "RiskProfile":
        value = value or {}
        return cls(
            overall_risk=value.get("overall_risk") or value.get("risk") or "MEDIUM",
            technical_risk=value.get("technical_risk") or "LOW",
            financial_risk=value.get("financial_risk") or "MEDIUM",
            operational_risk=value.get("operational_risk") or "LOW",
            reversibility=value.get("reversibility") or "MEDIUM",
            factors=value.get("factors") if isinstance(value.get("factors"), list) else [],
        )

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass
class Opportunity:
    """Standard object emitted by every optimizer before planning/execution."""

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
    schema_version: str = "6.1"

    def to_dict(self) -> JsonDict:
        payload = dict(self.payload or {})

        if self.risk_assessment and "risk_assessment" not in payload:
            payload["risk_assessment"] = self.risk_assessment.to_dict()

        result = {
            "optimizer": self.optimizer,
            "decision": self.decision,
            "title": self.title,
            "reason": self.reason,
            "confidence": self.confidence,
            "risk": self.risk,
            "estimated_monthly_impact": self.estimated_monthly_impact,
            "score": self.score,
            "payload": payload,
            "evidence": [item.to_dict() for item in self.evidence],
            "created_at": self.created_at,
            "schema_version": self.schema_version,
        }

        if self.impact:
            result["impact"] = self.impact.to_dict()

        if self.risk_assessment:
            result["risk_assessment"] = self.risk_assessment.to_dict()

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
