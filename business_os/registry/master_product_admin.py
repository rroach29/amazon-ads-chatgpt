"""Master Product admin actions.

Small, audited updates for correcting registry data during cleanup.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import or_

from database import SessionLocal
from business_registry.models import BusinessEvent, MasterProduct, ProductChannel


class MasterProductAdminService:
    version = "business-os-0.9.9-product-archive-restore"

    @classmethod
    def create_product(
        cls,
        name: str,
        brand: str | None = None,
        product_family: str | None = None,
        primary_sku: str | None = None,
        ean_upc: str | None = None,
        status: str = "Active",
        lifecycle_stage: str = "Idea",
        notes: str | None = None,
        template: str | None = None,
        marketplaces: str | None = None,
        approve: bool = False,
    ) -> dict[str, Any]:
        clean_name = (name or "").strip()
        if not approve:
            return {"status": "APPROVAL_REQUIRED", "version": cls.version, "message": "Product creation requires approve=true."}
        if not clean_name:
            return {"status": "ERROR", "version": cls.version, "message": "Product name is required."}
        db = SessionLocal()
        try:
            duplicate_candidates = cls._duplicate_candidates(db, clean_name, primary_sku, ean_upc)
            master_product_id = cls._next_master_product_id(db)
            product = MasterProduct(master_product_id=master_product_id, name=clean_name, brand=(brand or "").strip() or None, product_family=(product_family or "").strip() or None, primary_sku=(primary_sku or "").strip() or None, ean_upc=(ean_upc or "").strip() or None, status=status or "Active", lifecycle_stage=lifecycle_stage or "Idea", notes=notes, source="manual_product_create", raw={"template": template, "duplicate_candidates_at_create": duplicate_candidates}, active=True)
            db.add(product)
            db.flush()
            created_channels = []
            for channel, marketplace in cls._parse_marketplaces(marketplaces):
                identity = ProductChannel(master_product_id=master_product_id, brand=product.brand, primary_sku=product.primary_sku, channel=channel, marketplace=marketplace, status="Planned", raw={"source": "new_product_wizard", "placeholder": True})
                db.add(identity)
                db.flush()
                created_channels.append(cls._channel_payload(identity))
            event_id = cls._event(db, "MasterProductCreated", product, f"Created Master Product: {clean_name}", "Created from Product Workspace New Product workflow.", {"product": cls._payload(product), "marketplace_placeholders": created_channels, "duplicate_candidates": duplicate_candidates})
            db.commit()
            return {"status": "CREATED", "version": cls.version, "event_id": event_id, "product": cls._payload(product), "marketplace_placeholders": created_channels, "duplicate_candidates": duplicate_candidates}
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @classmethod
    def archive_product(cls, master_product_id: str, approve: bool = False, reason: str | None = None) -> dict[str, Any]:
        return cls._set_active_status(master_product_id, active=False, status="Archived", lifecycle_stage="Archived", event_type="MasterProductArchived", approve=approve, reason=reason)

    @classmethod
    def restore_product(cls, master_product_id: str, approve: bool = False, reason: str | None = None) -> dict[str, Any]:
        return cls._set_active_status(master_product_id, active=True, status="Active", lifecycle_stage=None, event_type="MasterProductRestored", approve=approve, reason=reason)

    @classmethod
    def _set_active_status(cls, master_product_id: str, active: bool, status: str, lifecycle_stage: str | None, event_type: str, approve: bool, reason: str | None) -> dict[str, Any]:
        if not approve:
            return {"status": "APPROVAL_REQUIRED", "version": cls.version, "message": f"{event_type} requires approve=true."}
        db = SessionLocal()
        try:
            product = db.query(MasterProduct).filter(MasterProduct.master_product_id == master_product_id).first()
            if not product:
                return {"status": "NOT_FOUND", "version": cls.version, "message": f"MasterProduct not found: {master_product_id}"}
            old = cls._payload(product)
            product.active = active
            product.status = status
            if lifecycle_stage:
                product.lifecycle_stage = lifecycle_stage
            product.updated_at = datetime.utcnow()
            raw = product.raw if isinstance(product.raw, dict) else {}
            raw.setdefault("lifecycle_history", []).append({"event_type": event_type, "old": old, "new_status": status, "active": active, "changed_at": product.updated_at.isoformat(), "reason": reason})
            product.raw = raw
            event_id = cls._event(db, event_type, product, f"{status} Master Product: {product.name}", reason or f"{event_type} from Product Workspace.", {"old": old, "new": cls._payload(product)})
            db.commit()
            return {"status": status.upper(), "version": cls.version, "event_id": event_id, "product": cls._payload(product)}
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @classmethod
    def update_title(cls, master_product_id: str, title: str, approve: bool = False, reason: str | None = None) -> dict[str, Any]:
        return cls.update_fields(master_product_id=master_product_id, approve=approve, reason=reason, name=title)

    @classmethod
    def update_fields(cls, master_product_id: str, approve: bool = False, reason: str | None = None, name: str | None = None, brand: str | None = None, product_family: str | None = None, primary_sku: str | None = None, ean_upc: str | None = None, status: str | None = None, lifecycle_stage: str | None = None) -> dict[str, Any]:
        if not approve:
            return {"status": "APPROVAL_REQUIRED", "version": cls.version, "message": "Master Product update requires approve=true."}
        proposed = {"name": name, "brand": brand, "product_family": product_family, "primary_sku": primary_sku, "ean_upc": ean_upc, "status": status, "lifecycle_stage": lifecycle_stage}
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
            changes = {field: {"old": getattr(product, field, None), "new": value} for field, value in cleaned.items() if getattr(product, field, None) != value}
            if not changes:
                return {"status": "NO_CHANGE", "version": cls.version, "product": cls._payload(product)}
            now = datetime.utcnow()
            raw = product.raw if isinstance(product.raw, dict) else {}
            raw.setdefault("field_history", []).append({"changes": changes, "changed_at": now.isoformat(), "reason": reason})
            product.raw = raw
            for field, values in changes.items():
                setattr(product, field, values["new"])
            product.updated_at = now
            event_id = cls._event(db, "MasterProductUpdated", product, f"Updated Master Product: {product.name}", reason or "Manual Master Product field edit.", {"master_product_id": product.master_product_id, "changes": changes})
            db.commit()
            return {"status": "UPDATED", "version": cls.version, "event_id": event_id, "changes": changes, "product": cls._payload(product)}
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def _event(db, event_type: str, product: MasterProduct, title: str, description: str | None, payload: dict[str, Any]) -> str:
        event_id = f"EV-{uuid4().hex[:12].upper()}"
        db.add(BusinessEvent(event_id=event_id, event_type=event_type, master_product_id=product.master_product_id, channel="Registry", title=title, description=description, source="master_product_admin", payload=payload))
        return event_id

    @staticmethod
    def _next_master_product_id(db) -> str:
        return f"MP-{uuid4().hex[:10].upper()}"

    @staticmethod
    def _parse_marketplaces(value: str | None) -> list[tuple[str, str | None]]:
        if not value:
            return []
        mapping = {"amazon_ca": ("Amazon", "CA"), "amazon_us": ("Amazon", "US"), "etsy": ("Etsy", "Global"), "shopify": ("Shopify", "Store"), "ebay": ("eBay", "Global")}
        return [mapping.get(token, (token.title(), None)) for token in [v.strip().lower() for v in value.split(",") if v.strip()]]

    @staticmethod
    def _duplicate_candidates(db, name: str, primary_sku: str | None, ean_upc: str | None = None) -> list[dict[str, Any]]:
        filters = [MasterProduct.name.ilike(f"%{name[:40]}%")]
        if primary_sku:
            filters.append(MasterProduct.primary_sku == primary_sku)
        if ean_upc:
            filters.append(MasterProduct.ean_upc == ean_upc)
        rows = db.query(MasterProduct).filter(or_(*filters)).limit(10).all()
        return [MasterProductAdminService._payload(row) for row in rows]

    @staticmethod
    def _payload(product: MasterProduct) -> dict[str, Any]:
        return {"master_product_id": product.master_product_id, "name": product.name, "brand": product.brand, "product_family": product.product_family, "primary_sku": product.primary_sku, "ean_upc": product.ean_upc, "status": product.status, "lifecycle_stage": product.lifecycle_stage, "active": product.active}

    @staticmethod
    def _channel_payload(channel: ProductChannel) -> dict[str, Any]:
        return {"id": channel.id, "master_product_id": channel.master_product_id, "channel": channel.channel, "marketplace": channel.marketplace, "asin": channel.asin, "sku": channel.sku, "status": channel.status}
