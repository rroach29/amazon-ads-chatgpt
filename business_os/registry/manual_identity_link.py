"""Manual marketplace identity linker.

Used by the Registry Gatekeeper review workflow to attach an Amazon listing to
an existing MasterProduct without creating a new product. This is the safe path
for review-required listings.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from database import SessionLocal
from business_registry.models import BusinessEvent, MasterProduct, ProductChannel


class ManualIdentityLinkService:
    version = "business-os-0.9.4-manual-identity-link"

    @classmethod
    def preview(
        cls,
        master_product_id: str,
        channel: str = "Amazon",
        marketplace: str | None = None,
        asin: str | None = None,
        sku: str | None = None,
        title: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        db = SessionLocal()
        try:
            product = db.query(MasterProduct).filter(MasterProduct.master_product_id == master_product_id).first()
            if not product:
                return {"status": "NOT_FOUND", "message": f"MasterProduct not found: {master_product_id}"}
            conflicts = cls._conflicts(db, master_product_id=master_product_id, channel=channel, marketplace=marketplace, asin=asin, sku=sku)
            existing = cls._existing_identity(db, master_product_id=master_product_id, channel=channel, marketplace=marketplace, asin=asin, sku=sku)
            return {
                "status": "OK",
                "version": cls.version,
                "read_only": True,
                "product": cls._product_payload(product),
                "identity": {"channel": channel, "marketplace": marketplace, "asin": asin, "sku": sku, "title": title, "status": status or "Manually Linked"},
                "existing_identity": cls._channel_payload(existing) if existing else None,
                "conflicts": conflicts,
                "safe_to_link": not conflicts,
                "will_create_identity": existing is None and not conflicts,
                "will_update_identity": existing is not None and not conflicts,
                "will_create_master_product": False,
            }
        finally:
            db.close()

    @classmethod
    def link(
        cls,
        master_product_id: str,
        channel: str = "Amazon",
        marketplace: str | None = None,
        asin: str | None = None,
        sku: str | None = None,
        title: str | None = None,
        status: str | None = None,
        approve: bool = False,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if not approve:
            return {"status": "APPROVAL_REQUIRED", "version": cls.version, "message": "Manual identity link requires approve=true after preview."}
        db = SessionLocal()
        try:
            product = db.query(MasterProduct).filter(MasterProduct.master_product_id == master_product_id).first()
            if not product:
                return {"status": "NOT_FOUND", "message": f"MasterProduct not found: {master_product_id}"}
            conflicts = cls._conflicts(db, master_product_id=master_product_id, channel=channel, marketplace=marketplace, asin=asin, sku=sku)
            if conflicts:
                return {"status": "BLOCKED_CONFLICT", "version": cls.version, "message": "Identity is already linked to another MasterProduct.", "conflicts": conflicts}
            identity = cls._existing_identity(db, master_product_id=master_product_id, channel=channel, marketplace=marketplace, asin=asin, sku=sku)
            action = "updated_identity"
            if not identity:
                action = "created_identity"
                identity = ProductChannel(master_product_id=product.master_product_id, brand=product.brand, primary_sku=product.primary_sku, channel=channel, marketplace=marketplace, channel_product_id=asin, channel_listing_id=asin, asin=asin, sku=sku, status=status or "Manually Linked", raw={"source": "manual_identity_link", "title": title, "reason": reason})
                db.add(identity)
            else:
                for attr, value in {"asin": asin, "sku": sku, "channel_product_id": asin, "channel_listing_id": asin, "status": status or "Manually Linked"}.items():
                    if value:
                        setattr(identity, attr, value)
                raw = identity.raw if isinstance(identity.raw, dict) else {}
                raw["manual_identity_link"] = {"title": title, "reason": reason, "linked_at": datetime.utcnow().isoformat()}
                identity.raw = raw
                identity.updated_at = datetime.utcnow()

            event_id = f"EV-{uuid4().hex[:12].upper()}"
            db.add(BusinessEvent(event_id=event_id, event_type="ManualMarketplaceIdentityLink", master_product_id=product.master_product_id, channel=channel, title=f"Linked {channel} identity to {product.name}", description=reason or "Manual marketplace identity link from Registry Gatekeeper.", source="manual_identity_link", payload={"action": action, "master_product_id": product.master_product_id, "channel": channel, "marketplace": marketplace, "asin": asin, "sku": sku, "title": title}))
            db.commit()
            return {"status": "LINKED", "version": cls.version, "action": action, "event_id": event_id, "product": cls._product_payload(product), "identity": cls._channel_payload(identity)}
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def _existing_identity(db, master_product_id: str, channel: str, marketplace: str | None, asin: str | None, sku: str | None):
        q = db.query(ProductChannel).filter(ProductChannel.master_product_id == master_product_id, ProductChannel.channel == channel)
        if marketplace:
            q = q.filter(ProductChannel.marketplace == marketplace)
        if asin:
            found = q.filter(ProductChannel.asin == asin).first()
            if found:
                return found
        if sku:
            found = q.filter(ProductChannel.sku == sku).first()
            if found:
                return found
        return None

    @staticmethod
    def _conflicts(db, master_product_id: str, channel: str, marketplace: str | None, asin: str | None, sku: str | None) -> list[dict[str, Any]]:
        conflicts = []
        q = db.query(ProductChannel).filter(ProductChannel.channel == channel, ProductChannel.master_product_id != master_product_id)
        if marketplace:
            q = q.filter(ProductChannel.marketplace == marketplace)
        if asin:
            for row in q.filter(ProductChannel.asin == asin).limit(10).all():
                conflicts.append({"type": "asin_already_linked", "identity": ManualIdentityLinkService._channel_payload(row)})
        if sku:
            for row in q.filter(ProductChannel.sku == sku).limit(10).all():
                conflicts.append({"type": "sku_already_linked", "identity": ManualIdentityLinkService._channel_payload(row)})
        return conflicts

    @staticmethod
    def _product_payload(product: MasterProduct) -> dict[str, Any]:
        return {"master_product_id": product.master_product_id, "name": product.name, "brand": product.brand, "product_family": product.product_family, "primary_sku": product.primary_sku, "status": product.status, "active": product.active}

    @staticmethod
    def _channel_payload(channel: ProductChannel) -> dict[str, Any]:
        return {"id": channel.id, "master_product_id": channel.master_product_id, "channel": channel.channel, "marketplace": channel.marketplace, "asin": channel.asin, "sku": channel.sku, "status": channel.status}
