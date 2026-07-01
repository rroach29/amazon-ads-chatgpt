"""Business OS Platform v1.0 — base scoring engine."""

from __future__ import annotations

from business_os.platform.scoring.models import ScoreComponent, ScoreResult


class BaseScoringEngine:
    version = "platform-1.0"

    @staticmethod
    def clamp(value: float, minimum: int = 0, maximum: int = 100) -> int:
        try:
            value = float(value)
        except Exception:
            value = 0
        return int(max(minimum, min(maximum, round(value))))

    @classmethod
    def combine(cls, name: str, components: list[ScoreComponent], explanation: str | None = None) -> ScoreResult:
        if not components:
            return ScoreResult(name=name, score=0, confidence=0, components=[], explanation=explanation, version=cls.version)

        total_weight = sum(component.weight for component in components) or 1.0
        score = sum(component.score * component.weight for component in components) / total_weight
        confidence = sum(component.confidence * component.weight for component in components) / total_weight

        evidence_summary = []
        for component in components:
            for evidence in component.evidence:
                evidence_summary.append(evidence.to_dict())

        return ScoreResult(
            name=name,
            score=cls.clamp(score),
            confidence=cls.clamp(confidence * 100 if confidence <= 1 else confidence),
            components=components,
            evidence_summary=evidence_summary,
            explanation=explanation,
            version=cls.version,
        )
