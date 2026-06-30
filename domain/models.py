"""
Business OS v8.3 — Typed Domain Models + Decision Provenance

Shared contracts for opportunities, decisions, initiatives, plans, objectives,
evidence, risk, impact, and outcomes. These models are intentionally additive:
existing dict-shaped responses continue to work while new services can use
validated domain objects internally.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


JsonDict = Dict[str, Any]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DomainBaseModel(BaseModel):
    """Base model with helpers for legacy dict compatibility."""

    class Config:
        use_enum_values = True
        arbitrary_types_allowed = True

    def to_dict(self) -> JsonDict:
        try:
            return self.model_dump(exclude_none=True)  # pydantic v2
        except AttributeError:
            return self.dict(exclude_none=True)  # pydantic v1


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PriorityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class LifecycleState(str, Enum):
    NEW = "NEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    UNDONE = "UNDONE"


class DecisionType(str, Enum):
    ADD_NEGATIVE_KEYWORD = "ADD_NEGATIVE_KEYWORD"
    HARVEST_KEYWORD = "HARVEST_KEYWORD"
    INCREASE_BID = "INCREASE_BID"
    REDUCE_BID = "REDUCE_BID"
    INCREASE_BUDGET = "INCREASE_BUDGET"
    DECREASE_BUDGET = "DECREASE_BUDGET"
    PAUSE_CAMPAIGN = "PAUSE_CAMPAIGN"
    PLACEMENT_MODIFIER = "PLACEMENT_MODIFIER"
    DAYPARTING = "DAYPARTING"
    UNKNOWN = "UNKNOWN"


class ObjectiveType(str, Enum):
    MAXIMIZE_PROFIT = "MAXIMIZE_PROFIT"
    MAXIMIZE_REVENUE = "MAXIMIZE_REVENUE"
    PRESERVE_CASH = "PRESERVE_CASH"
    LAUNCH_PRODUCT = "LAUNCH_PRODUCT"
    DEFEND_RANK = "DEFEND_RANK"
    REDUCE_WASTE = "REDUCE_WASTE"
    BALANCED_GROWTH = "BALANCED_GROWTH"


class ExecutionPhase(str, Enum):
    PLAN = "PLAN"
    REVIEW = "REVIEW"
    APPROVE = "APPROVE"
    EXECUTE = "EXECUTE"
    MEASURE = "MEASURE"
    LEARN = "LEARN"


# Backward-readable alias for planning terminology.
StrategicObjective = ObjectiveType


class DecisionProvenance(DomainBaseModel):
    optimizer_name: str = "unknown"
    optimizer_version: Optional[str] = None
    optimizer_class: Optional[str] = None
    optimizer_capability: Optional[str] = None
    business_os_version: str = "8.3"
    decision_factory_version: str = "2.0"
    generated_at: str = Field(default_factory=utc_now_iso)
    data_context: JsonDict = Field(default_factory=dict)
    business_objective: str = ObjectiveType.MAXIMIZE_PROFIT.value
    source_opportunity_id: Optional[str] = None


class OptimizerManifest(DomainBaseModel):
    name: str
    version: str = "unknown"
    optimizer_class: str = "unknown"
    decision_types: List[str] = Field(default_factory=list)
    supported_objectives: List[str] = Field(default_factory=lambda: [ObjectiveType.MAXIMIZE_PROFIT.value])
    capabilities: List[str] = Field(default_factory=list)
    risk_profile: RiskLevel = RiskLevel.MEDIUM
    schema_version: str = "8.3"


class Evidence(DomainBaseModel):
    source: str = "unknown"
    metric: str = "unknown"
    value: Any = None
    description: str = ""
    weight: float = 1.0
    confidence: Optional[float] = None
    observed_at: Optional[str] = None


class ImpactEstimate(DomainBaseModel):
    estimated_monthly_impact: float = 0.0
    estimated_monthly_revenue: Optional[float] = None
    estimated_monthly_profit: Optional[float] = None
    currency: Optional[str] = None
    basis: str = "heuristic"
    confidence: Optional[float] = None


class RiskAssessment(DomainBaseModel):
    technical_risk: RiskLevel = RiskLevel.LOW
    financial_risk: RiskLevel = RiskLevel.MEDIUM
    operational_risk: RiskLevel = RiskLevel.LOW
    reversibility: str = "MEDIUM"
    overall_risk: RiskLevel = RiskLevel.MEDIUM
    factors: List[str] = Field(default_factory=list)

    @classmethod
    def from_any(cls, value: Any) -> "RiskAssessment":
        if isinstance(value, RiskAssessment):
            return value
        if isinstance(value, dict):
            raw = dict(value)
            raw["overall_risk"] = raw.get("overall_risk") or raw.get("risk") or "MEDIUM"
            return cls(**raw)
        return cls()


class Opportunity(DomainBaseModel):
    opportunity_id: str = Field(default_factory=lambda: str(uuid4()))
    optimizer_name: str = "unknown"
    optimizer_version: Optional[str] = None
    optimizer_class: Optional[str] = None
    business_objective: str = ObjectiveType.MAXIMIZE_PROFIT.value
    decision: str = DecisionType.UNKNOWN.value
    title: str = ""
    reason: str = ""
    confidence: float = 0.0
    risk: RiskLevel = RiskLevel.MEDIUM
    priority: PriorityLevel = PriorityLevel.MEDIUM
    estimated_monthly_impact: float = 0.0
    score: float = 0.0
    payload: JsonDict = Field(default_factory=dict)
    evidence: List[Evidence] = Field(default_factory=list)
    impact: Optional[ImpactEstimate] = None
    risk_assessment: Optional[RiskAssessment] = None
    created_at: str = Field(default_factory=utc_now_iso)
    schema_version: str = "8.3"

    @classmethod
    def from_legacy(cls, item: JsonDict) -> "Opportunity":
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        evidence = item.get("evidence") or payload.get("evidence") or []
        return cls(
            opportunity_id=str(item.get("opportunity_id") or item.get("id") or uuid4()),
            optimizer_name=str(item.get("optimizer_name") or item.get("optimizer") or item.get("source") or "unknown"),
            optimizer_version=item.get("optimizer_version"),
            optimizer_class=item.get("optimizer_class") or payload.get("optimizer_class"),
            business_objective=str(item.get("business_objective") or payload.get("business_objective") or ObjectiveType.MAXIMIZE_PROFIT.value),
            decision=str(item.get("decision") or DecisionType.UNKNOWN.value),
            title=str(item.get("title") or item.get("recommended_action") or ""),
            reason=str(item.get("reason") or ""),
            confidence=float(item.get("confidence") or 0),
            risk=str(item.get("risk") or payload.get("risk") or "MEDIUM").upper(),
            priority=str(item.get("priority") or "MEDIUM").upper(),
            estimated_monthly_impact=float(item.get("estimated_monthly_impact") or 0),
            score=float(item.get("score") or 0),
            payload=payload,
            evidence=[Evidence(**e) for e in evidence if isinstance(e, dict)],
            impact=ImpactEstimate(**item.get("impact")) if isinstance(item.get("impact"), dict) else None,
            risk_assessment=RiskAssessment.from_any(item.get("risk_assessment") or payload.get("risk_assessment")),
            created_at=str(item.get("created_at") or utc_now_iso()),
        )


class Decision(DomainBaseModel):
    decision_id: Optional[Any] = None
    stable_id: str = Field(default_factory=lambda: str(uuid4()))
    decision: str = DecisionType.UNKNOWN.value
    priority: PriorityLevel = PriorityLevel.MEDIUM
    confidence: float = 0.0
    risk: RiskLevel = RiskLevel.MEDIUM
    estimated_monthly_impact: float = 0.0
    reasoning: List[str] = Field(default_factory=list)
    recommended_action: str = ""
    payload: JsonDict = Field(default_factory=dict)
    evidence: List[Evidence] = Field(default_factory=list)
    lifecycle_state: LifecycleState = LifecycleState.NEW
    optimizer_name: str = "unknown"
    optimizer_version: Optional[str] = None
    optimizer_class: Optional[str] = None
    business_os_version: str = "8.3"
    decision_factory_version: str = "2.0"
    business_objective: str = ObjectiveType.MAXIMIZE_PROFIT.value
    source_opportunity_id: Optional[str] = None
    provenance: Optional[DecisionProvenance] = None
    source: str = "optimizer"
    created_at: str = Field(default_factory=utc_now_iso)
    schema_version: str = "8.3"

    @classmethod
    def from_legacy(cls, item: JsonDict) -> "Decision":
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        evidence = item.get("evidence") or payload.get("evidence") or []
        return cls(
            decision_id=item.get("decision_id") or item.get("id"),
            stable_id=str(item.get("stable_id") or item.get("uuid") or uuid4()),
            decision=str(item.get("decision") or DecisionType.UNKNOWN.value),
            priority=str(item.get("priority") or "MEDIUM").upper(),
            confidence=float(item.get("confidence") or 0),
            risk=str(item.get("risk") or "MEDIUM").upper(),
            estimated_monthly_impact=float(item.get("estimated_monthly_impact") or 0),
            reasoning=item.get("reasoning") if isinstance(item.get("reasoning"), list) else [],
            recommended_action=str(item.get("recommended_action") or ""),
            payload=payload,
            evidence=[Evidence(**e) for e in evidence if isinstance(e, dict)],
            lifecycle_state=str(item.get("lifecycle_state") or "NEW").upper(),
            optimizer_name=str(item.get("optimizer_name") or item.get("optimizer") or payload.get("optimizer_name") or "unknown"),
            optimizer_version=item.get("optimizer_version") or payload.get("optimizer_version"),
            optimizer_class=item.get("optimizer_class") or payload.get("optimizer_class"),
            business_os_version=str(item.get("business_os_version") or payload.get("business_os_version") or "8.3"),
            decision_factory_version=str(item.get("decision_factory_version") or payload.get("decision_factory_version") or "2.0"),
            business_objective=str(item.get("business_objective") or payload.get("business_objective") or ObjectiveType.MAXIMIZE_PROFIT.value),
            source_opportunity_id=item.get("source_opportunity_id") or payload.get("source_opportunity_id"),
            provenance=DecisionProvenance(**item.get("provenance")) if isinstance(item.get("provenance"), dict) else None,
            source=str(item.get("source") or "optimizer"),
            created_at=str(item.get("created_at") or utc_now_iso()),
        )


class Objective(DomainBaseModel):
    objective_id: str = ObjectiveType.BALANCED_GROWTH.value
    label: str = "Balanced Growth"
    description: str = "Balance growth, efficiency, risk, and cash preservation."
    risk_tolerance: RiskLevel = RiskLevel.MEDIUM
    growth_weight: float = 1.0
    efficiency_weight: float = 1.0
    cash_weight: float = 1.0
    profit_weight: float = 1.0


class ActionGroup(DomainBaseModel):
    group_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = ""
    actions: List[Decision] = Field(default_factory=list)
    estimated_monthly_impact: float = 0.0
    confidence: float = 0.0
    risk: RiskLevel = RiskLevel.MEDIUM
    execution_phase: ExecutionPhase = ExecutionPhase.PLAN


class Initiative(DomainBaseModel):
    initiative_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = ""
    objective: Optional[str] = None
    action_groups: List[ActionGroup] = Field(default_factory=list)
    estimated_monthly_impact: float = 0.0
    confidence: float = 0.0
    risk: RiskLevel = RiskLevel.MEDIUM
    priority_score: float = 0.0
    narrative: str = ""


class Plan(DomainBaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = "Executive Plan"
    objective: Optional[Objective] = None
    initiatives: List[Initiative] = Field(default_factory=list)
    estimated_monthly_impact: float = 0.0
    confidence: float = 0.0
    risk: RiskLevel = RiskLevel.MEDIUM
    created_at: str = Field(default_factory=utc_now_iso)
    schema_version: str = "8.3"


class Outcome(DomainBaseModel):
    decision_id: Optional[Any] = None
    decision: str = DecisionType.UNKNOWN.value
    estimated_impact: float = 0.0
    actual_impact: float = 0.0
    variance: float = 0.0
    status: str = "PENDING"
    evaluation_period_days: int = 14
    recorded_at: str = Field(default_factory=utc_now_iso)
