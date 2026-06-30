"""
Business OS v7.0 — Knowledge Graph Models

Small typed contracts used by the relationship layer. These are intentionally
lightweight and serializable so Mission Control, optimizers, learning services,
and future non-Amazon agents can share the same relationship vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class BusinessNode:
    node_id: str
    node_type: str
    label: str
    source: str = "amazon_ads"
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.node_id,
            "type": self.node_type,
            "label": self.label,
            "source": self.source,
            "attributes": self.attributes,
        }


@dataclass(frozen=True)
class BusinessEdge:
    source_id: str
    target_id: str
    relationship: str
    weight: float = 1.0
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source_id,
            "target": self.target_id,
            "relationship": self.relationship,
            "weight": self.weight,
            "evidence": self.evidence,
        }


@dataclass
class KnowledgeGraphSnapshot:
    status: str
    generated_at: str
    scope: dict[str, Any]
    nodes: list[BusinessNode]
    edges: list[BusinessEdge]
    summary: dict[str, Any]

    @classmethod
    def build(
        cls,
        *,
        scope: dict[str, Any],
        nodes: list[BusinessNode],
        edges: list[BusinessEdge],
        summary: dict[str, Any] | None = None,
        status: str = "OK",
    ) -> "KnowledgeGraphSnapshot":
        return cls(
            status=status,
            generated_at=datetime.utcnow().isoformat() + "Z",
            scope=scope,
            nodes=nodes,
            edges=edges,
            summary=summary or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "generated_at": self.generated_at,
            "scope": self.scope,
            "summary": self.summary,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }
