"""Business OS Platform v1.0 — Score models.

All future intelligence scores should follow this shape:
- score
- confidence
- evidence
- explanation
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from business_os.platform.evidence.models import EvidenceItem


@dataclass
class ScoreComponent:
    name: str
    score: float
    weight: float = 1.0
    confidence: float = 1.0
    evidence: list[EvidenceItem] = field(default_factory=list)
    explanation: str | None = None

    def weighted_score(self) -> float:
        return self.score * self.weight


@dataclass
class ScoreResult:
    name: str
    score: int
    confidence: int
    components: list[ScoreComponent] = field(default_factory=list)
    evidence_summary: list[dict[str, Any]] = field(default_factory=list)
    explanation: str | None = None
    version: str = "platform-1.0"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data
