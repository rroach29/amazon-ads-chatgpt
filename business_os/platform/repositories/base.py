"""Business OS Platform v1.0 — repository base.

Repositories isolate database access from engines and services.
"""

from __future__ import annotations

from database import SessionLocal


class BaseRepository:
    def __init__(self, db=None):
        self._external_db = db is not None
        self.db = db or SessionLocal()

    def close(self):
        if not self._external_db and self.db:
            self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
