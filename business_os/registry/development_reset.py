"""Development-only Product Registry reset.

This is intentionally destructive and intended only while the registry is test data.
It clears product registry tables so imports can rebuild clean Master Products from
Amazon first, then future channels like Etsy can match against that canonical set.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from database import SessionLocal
from business_registry.models import BusinessEvent, MasterProduct, ProductChannel, ProductScore


class DevelopmentRegistryResetService:
    version = "business-os-1.0.0-development-registry-reset"
    required_phrase = "RESET PRODUCT REGISTRY"

    @classmethod
    def preview(cls) -> dict[str, Any]:
        db = SessionLocal()
        try:
            return {
                "status": "PREVIEW",
                "version": cls.version,
                "destructive": True,
                "required_confirmation": cls.required_phrase,
                "will_delete": cls._counts(db),
                "will_preserve": ["settings", "environment variables", "API connections", "frontend configuration"],
                "recommended_rebuild_order": ["Amazon CA sync", "Amazon US sync", "Etsy sync when integrated"],
            }
        finally:
            db.close()

    @classmethod
    def reset(cls, confirm: str | None = None, approve: bool = False) -> dict[str, Any]:
        if not approve or confirm != cls.required_phrase:
            return {"status": "APPROVAL_REQUIRED", "version": cls.version, "required_confirmation": cls.required_phrase}
        db = SessionLocal()
        try:
            before = cls._counts(db)
            db.query(ProductScore).delete(synchronize_session=False)
            db.query(ProductChannel).delete(synchronize_session=False)
            db.query(MasterProduct).delete(synchronize_session=False)
            event_id = f"EV-{uuid4().hex[:12].upper()}"
            db.add(BusinessEvent(event_id=event_id, event_type="DevelopmentRegistryReset", channel="Registry", title="Development Product Registry reset", description="Deleted Master Products, Product Channels, and Product Scores so registry can be rebuilt from marketplace imports.", source="development_registry_reset", payload={"deleted": before, "confirmation": confirm}))
            db.commit()
            return {"status": "RESET_COMPLETE", "version": cls.version, "event_id": event_id, "deleted": before, "next_steps": ["Run Amazon CA Listings sync with create_missing_products=true", "Run Amazon US Listings sync with create_missing_products=true", "Review Duplicate Cluster Review"]}
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def _counts(db) -> dict[str, int]:
        return {
            "master_products": db.query(MasterProduct).count(),
            "product_channels": db.query(ProductChannel).count(),
            "product_scores": db.query(ProductScore).count(),
        }
