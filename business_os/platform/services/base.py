"""Business OS Platform v1.0 — service base.

Services orchestrate engines/repositories and are called by routes.
Routes should stay thin.
"""

from __future__ import annotations

from typing import Any


class BaseService:
    version = "platform-1.0"

    @classmethod
    def response(cls, status: str = "OK", payload: dict[str, Any] | None = None, **extra):
        return {
            "status": status,
            "version": cls.version,
            **(payload or {}),
            **extra,
        }
