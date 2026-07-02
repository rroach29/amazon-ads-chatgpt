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
    version = "business-os-0.9.6-master-product-field-edit"
    EDITABLE_FIELDS = {"name", "brand", "product_family", "primary_sku", "status", "lifecycle_stage"}

    @classmethod
    def update_title(cls, master_product_id: str, title: str, approve: bool = False, reason: str | None = None) -> dict[str, Any]:
        return cls.update_fields(master_product_id=master_product_id, approve=approve, reason=reason, name=title)

    @classmethod
    def update_fields(
        cls,
        master_product_id: str,
        approve: bool = False,
        reason: str | None = None,
        name: str | None = None,
        brand: str | None = None,
        product_family: str | None = None,
        primary_sku: str | None = None,
        status: str | None = None,
        lifecycle_stage: str | None = None,
    ) -> dict[str, Any]:
        if not approve:
            return {"status": "APPROVAL_REQUIRED", "version": cls.version, "message": "Master Product update requires approve=true."}

        proposed = {
            "name": name,
            "brand": brand,
            "product_family": product_family,
            "primary_sku": primary_sku,
            "status": status,
            "lifecycle_stage": lifecycle_stage,
        }
        cleaned = {}
        for field, value in proposed.items():
            if value is None:
                continue
            text = str(value).strip()
            if field == "name" and not text:
                return {"status": "ERROR", "version": cls.version, "message": "Title cannot be blank."}
            if len(text) > 500:
                return {"status": "ERROR", "version": cls.version, "message": f"{field} is too long. Maximum length is 500 characters."}
            cleaned[field] = text
        if not cleaned:
            return {"status": "NO_CHANGE", "version": cls.version, "message": "No editable fields supplied."}

        db = SessionLocal()
        try:
            product = db.query(MasterProduct).filter(MasterProduct.master_product_id == master_product_id).first()
            if not product:
                return {"status": "NOT_FOUND", "version": cls.version, "message": f"MasterProduct not found: {master_product_id}"}

            changes = {}
            for field, value in cleaned.items():
                old_value = getattr(product, field, None)
                if old_value != value:
                    changes[field] = {"old": old_value, "new": value}
            if not changes:
                return {"status": "NO_CHANGE", "version": cls.version, "product": cls._payload(product)}

            now = datetime.utcnow()
            raw = product.raw if isinstance(product.raw, dict) else {}
            raw.setdefault("field_history", []).append({"changes": changes, "changed_at": now.isoformat(), "reason": reason})
            if "name" in changes:
                raw.setdefault("title_history", []).append({"old_title": changes["name"]["old"], "new_title": changes["name"]["new"], "changed_at": now.isoformat(), "reason": reason})
            product.raw = raw
            for field, values in changes.items():
                setattr(product, field, values["new"])
            product.updated_at = now

            event_id = f"EV-{uuid4().hex[:12].upper()}"
            db.add(BusinessEvent(
                event_id=event_id,
                event_type="MasterProductUpdated",
                master_product_id=product.master_product_id,
                channel="Registry",
                title=f"Updated Master Product: {product.name}",
                description=reason or "Manual Master Product field edit.",
                source="master_product_admin",
                payload={"master_product_id": product.master_product_id, "changes": changes},
            ))
            db.commit()
            return {"status": "UPDATED", "version": cls.version, "event_id": event_id, "changes": changes, "product": cls._payload(product)}
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def _payload(product: MasterProduct) -> dict[str, Any]:
        return {"master_product_id": product.master_product_id, "name": product.name, "brand": product.brand, "product_family": product.product_family, "primary_sku": product.primary_sku, "status": product.status, "lifecycle_stage": product.lifecycle_stage, "active": product.active}
