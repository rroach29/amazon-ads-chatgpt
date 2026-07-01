"""Business OS Platform v1.0 — Evidence models.

Evidence is the foundation for explainable intelligence.
Every score, recommendation, and executive insight should eventually point back to evidence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class EvidenceItem:
    source: str
    signal: str
    value: Any = None
    weight: float = 1.0
    confidence: float = 1.0
    explanation: str | None = None
    observed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceSet:
    items: list[EvidenceItem] = field(default_factory=list)

    def add(
        self,
        source: str,
        signal: str,
        value: Any = None,
        weight: float = 1.0,
        confidence: float = 1.0,
        explanation: str | None = None,
    ) -> "EvidenceSet":
        self.items.append(
            EvidenceItem(
                source=source,
                signal=signal,
                value=value,
                weight=weight,
                confidence=confidence,
                explanation=explanation,
            )
        )
        return self

    def confidence(self) -> float:
        if not self.items:
            return 0.0
        weighted = sum(item.confidence * item.weight for item in self.items)
        weight = sum(item.weight for item in self.items) or 1.0
        return round(weighted / weight, 4)

    def to_list(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.items]
