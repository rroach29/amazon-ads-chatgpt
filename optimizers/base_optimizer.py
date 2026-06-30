"""
Business OS v6.1.0
Base Optimizer

Every optimizer follows the same lifecycle:
collect -> detect -> estimate impact -> assess risk -> build decisions
"""

from abc import ABC, abstractmethod
from time import perf_counter

from optimizers.domain_models import OptimizerRunMetrics


class BaseOptimizer(ABC):
    name = "base_optimizer"
    version = "6.1.0"
    decision_types = []

    def __init__(self, context=None):
        self.context = context or {}
        self.data = None
        self.opportunities = []
        self.decisions = []
        self.metrics = OptimizerRunMetrics(optimizer=self.name)

    @abstractmethod
    def collect(self):
        """Load required data for this optimizer."""
        raise NotImplementedError

    @abstractmethod
    def detect(self):
        """Find opportunities."""
        raise NotImplementedError

    @abstractmethod
    def estimate_impact(self):
        """Attach estimated impact to opportunities."""
        raise NotImplementedError

    @abstractmethod
    def assess_risk(self):
        """Attach structured risk to opportunities."""
        raise NotImplementedError

    @abstractmethod
    def build_decisions(self):
        """Convert opportunities into standardized decision objects."""
        raise NotImplementedError

    def run(self):
        started = perf_counter()

        try:
            self.collect()
            self.detect()
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
            "decision_types": self.decision_types,
            "context": self.context,
            "opportunity_count": len(self.opportunities),
            "decision_count": len(self.decisions),
            "opportunities": self.opportunities,
            "decisions": self.decisions,
            "metrics": self.metrics.to_dict(),
        }
