"""
Business OS v8.3
Base Optimizer

Every optimizer follows the same lifecycle and now publishes a manifest plus
provenance metadata for all opportunities and decisions it emits.
"""

from abc import ABC, abstractmethod
from time import perf_counter

from domain import OptimizerManifest
from optimizers.domain_models import OptimizerRunMetrics


class BaseOptimizer(ABC):
    name = "base_optimizer"
    version = "6.1.0"
    decision_types = []
    capabilities = []
    supported_objectives = ["MAXIMIZE_PROFIT"]
    risk_profile = "MEDIUM"

    def __init__(self, context=None):
        self.context = context or {}
        self.data = None
        self.opportunities = []
        self.decisions = []
        self.metrics = OptimizerRunMetrics(optimizer=self.name)

    @classmethod
    def manifest(cls):
        return OptimizerManifest(
            name=cls.name,
            version=getattr(cls, "version", "unknown"),
            optimizer_class=cls.__name__,
            decision_types=list(getattr(cls, "decision_types", []) or []),
            supported_objectives=list(getattr(cls, "supported_objectives", ["MAXIMIZE_PROFIT"]) or []),
            capabilities=list(getattr(cls, "capabilities", []) or []),
            risk_profile=getattr(cls, "risk_profile", "MEDIUM"),
        ).to_dict()

    def _attach_provenance_to_opportunities(self):
        enriched = []
        for opportunity in self.opportunities or []:
            if not isinstance(opportunity, dict):
                enriched.append(opportunity)
                continue
            opportunity.setdefault("optimizer_name", self.name)
            opportunity.setdefault("optimizer", self.name)
            opportunity.setdefault("optimizer_version", self.version)
            opportunity.setdefault("optimizer_class", self.__class__.__name__)
            opportunity.setdefault("business_objective", "MAXIMIZE_PROFIT")
            payload = opportunity.get("payload") if isinstance(opportunity.get("payload"), dict) else {}
            payload.setdefault("optimizer_name", self.name)
            payload.setdefault("optimizer_version", self.version)
            payload.setdefault("optimizer_class", self.__class__.__name__)
            payload.setdefault("business_objective", opportunity.get("business_objective", "MAXIMIZE_PROFIT"))
            payload.setdefault("source_opportunity_id", opportunity.get("opportunity_id"))
            opportunity["payload"] = payload
            enriched.append(opportunity)
        self.opportunities = enriched

    @abstractmethod
    def collect(self):
        raise NotImplementedError

    @abstractmethod
    def detect(self):
        raise NotImplementedError

    @abstractmethod
    def estimate_impact(self):
        raise NotImplementedError

    @abstractmethod
    def assess_risk(self):
        raise NotImplementedError

    @abstractmethod
    def build_decisions(self):
        raise NotImplementedError

    def run(self):
        started = perf_counter()

        try:
            self.collect()
            self.detect()
            self._attach_provenance_to_opportunities()
            self.estimate_impact()
            self.assess_risk()
            self.build_decisions()
            self.metrics.status = "OK"
        except Exception as exc:
            self.metrics.status = "ERROR"
            self.metrics.error = str(exc)
            self.opportunities = []
            self.decisions = []

        self.metrics.runtime_ms = round((perf_counter() - started) * 1000, 2)
        self.metrics.opportunity_count = len(self.opportunities)
        self.metrics.decision_count = len(self.decisions)

        return {
            "status": self.metrics.status,
            "optimizer": self.name,
            "optimizer_version": self.version,
            "optimizer_manifest": self.manifest(),
            "decision_types": self.decision_types,
            "context": self.context,
            "opportunity_count": len(self.opportunities),
            "decision_count": len(self.decisions),
            "opportunities": self.opportunities,
            "decisions": self.decisions,
            "metrics": self.metrics.to_dict(),
        }
