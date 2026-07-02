"""Master Product admin actions.

Small, audited updates for correcting registry data during cleanup.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from database import SessionLocal
from business_registry.models import BusinessEvent, MasterProduct


class MasterProductAdminService:
    version = "business-os-0.9.5-master-product-title-edit"

    @classmethod
    def update_title(
        cls,
        master_product_id: str,
        title: str,
        approve: bool = False,
        reason: str | None = None,
    ) -> dict[str, Any]:
        clean_title = (title or "").strip()
        if not approve:
            return {"status": "APPROVAL_REQUIRED", "version": cls.version, "message": "Title update requires approve=true."}
        if not clean_title:
            return {"status": "ERROR", "version": cls.version, "message": "Title cannot be blank."}
        if len(clean_title) > 500:
            return {"status": "ERROR", "version": cls.version, "message": "Title is too long. Maximum length is 500 characters."}

        db = SessionLocal()
        try:
            product = db.query(MasterProduct).filter(MasterProduct.master_product_id == master_product_id).first()
            if not product:
                return {"status": "NOT_FOUND", "version": cls.version, "message": f"MasterProduct not found: {master_product_id}"}
            old_title = product.name
            if old_title == clean_title:
                return {"status": "NO_CHANGE", "version": cls.version, "product": cls._payload(product)}

            now = datetime.utcnow()
            raw = product.raw if isinstance(product.raw, dict) else {}
            raw.setdefault("title_history", []).append({"old_title": old_title, "new_title": clean_title, "changed_at": now.isoformat(), "reason": reason})
            product.raw = raw
            product.name = clean_title
            product.updated_at = now

            event_id = f"EV-{uuid4().hex[:12].upper()}"
            db.add(BusinessEvent(
                event_id=event_id,
                event_type="MasterProductTitleUpdated",
                master_product_id=product.master_product_id,
                channel="Registry",
                title=f"Updated Master Product title: {clean_title}",
                description=reason or "Manual Master Product title edit.",
                source="master_product_admin",
                payload={"master_product_id": product.master_product_id, "old_title": old_title, "new_title": clean_title},
            ))
            db.commit()
            return {"status": "UPDATED", "version": cls.version, "event_id": event_id, "old_title": old_title, "new_title": clean_title, "product": cls._payload(product)}
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def _payload(product: MasterProduct) -> dict[str, Any]:
        return {"master_product_id": product.master_product_id, "name": product.name, "brand": product.brand, "product_family": product.product_family, "primary_sku": product.primary_sku, "status": product.status, "active": product.active}
