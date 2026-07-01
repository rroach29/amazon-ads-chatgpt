"""Business OS Platform v1.0 — engine base classes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class EngineResult:
    status: str
    version: str
    payload: dict[str, Any]
    explanation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "version": self.version,
            "payload": self.payload,
            "explanation": self.explanation,
        }


class BaseEngine:
    version = "platform-1.0"

    @classmethod
    def ok(cls, payload: dict[str, Any], explanation: str | None = None) -> EngineResult:
        return EngineResult(status="OK", version=cls.version, payload=payload, explanation=explanation)

    @classmethod
    def error(cls, message: str, payload: dict[str, Any] | None = None) -> EngineResult:
        return EngineResult(status="ERROR", version=cls.version, payload=payload or {"message": message}, explanation=message)
