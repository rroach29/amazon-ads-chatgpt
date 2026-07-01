"""Business Core v1.0 — Business Registry service."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from database import SessionLocal
from business_registry.models import BusinessEvent, MasterProduct, ProductChannel
from business_registry.seed_data import MASTER_PRODUCT_SEED


class BusinessRegistryService:
    version = "business-core-1.0"

    @staticmethod
    def health() -> dict[str, Any]:
        db = SessionLocal()
        try:
            return {
                "status": "OK",
                "version": BusinessRegistryService.version,
                "counts": {
                    "master_products": db.query(MasterProduct).count(),
                    "product_channels": db.query(ProductChannel).count(),
                    "business_events": db.query(BusinessEvent).count(),
                },
                "message": "Business Registry is the canonical identity layer for Master Products and channel mappings.",
            }
        finally:
            db.close()

    @staticmethod
    def seed_master_products(overwrite: bool = False) -> dict[str, Any]:
        db = SessionLocal()
        created = 0
        updated = 0
        channels_created = 0
        channels_updated = 0
        events_created = 0

        try:
            for row in MASTER_PRODUCT_SEED:
                mpid = row["master_product_id"]
                existing = db.query(MasterProduct).filter(MasterProduct.master_product_id == mpid).first()

                if existing and not overwrite:
                    continue

                payload = {
                    "master_product_id": mpid,
                    "brand": row.get("brand"),
                    "product_family": row.get("product_family"),
                    "primary_sku": row.get("primary_sku"),
                    "ean_upc": row.get("ean_upc"),
                    "name": row.get("name") or mpid,
                    "status": row.get("status") or "Active",
                    "lifecycle_stage": row.get("lifecycle_stage") or "Unassigned",
                    "primary_channel_strategy": row.get("primary_channel_strategy"),
                    "notes": row.get("notes"),
                    "source": row.get("source"),
                    "raw": row,
                    "active": True,
                    "updated_at": datetime.utcnow(),
                }

                if existing:
                    for key, value in payload.items():
                        setattr(existing, key, value)
                    updated += 1
                else:
                    db.add(MasterProduct(**payload))
                    created += 1

                for channel_row in BusinessRegistryService._default_channel_rows(row):
                    existing_channel = (
                        db.query(ProductChannel)
                        .filter(ProductChannel.master_product_id == mpid)
                        .filter(ProductChannel.channel == channel_row["channel"])
                        .first()
                    )
                    if existing_channel and not overwrite:
                        continue
                    if existing_channel:
                        for key, value in channel_row.items():
                            setattr(existing_channel, key, value)
                        existing_channel.updated_at = datetime.utcnow()
                        channels_updated += 1
                    else:
                        db.add(ProductChannel(**channel_row))
                        channels_created += 1

                if not db.query(BusinessEvent).filter(BusinessEvent.event_id == f"seed-{mpid}").first():
                    db.add(
                        BusinessEvent(
                            event_id=f"seed-{mpid}",
                            event_type="MasterProductSeeded",
                            master_product_id=mpid,
                            title=f"Master Product seeded: {row.get('name') or mpid}",
                            description="Imported from the user's master SKU workbook.",
                            source="business_registry_seed",
                            payload=row,
                        )
                    )
                    events_created += 1

            db.commit()
            return {
                "status": "OK",
                "version": BusinessRegistryService.version,
                "master_products_created": created,
                "master_products_updated": updated,
                "product_channels_created": channels_created,
                "product_channels_updated": channels_updated,
                "business_events_created": events_created,
                "overwrite": overwrite,
                "message": "Master Product Registry seeded from existing SKU workbook data.",
            }
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": BusinessRegistryService.version, "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def list_master_products(
        brand: str | None = None,
        product_family: str | None = None,
        status: str | None = None,
        limit: int = 250,
    ) -> dict[str, Any]:
        db = SessionLocal()
        try:
            query = db.query(MasterProduct)
            if brand:
                query = query.filter(MasterProduct.brand == brand)
            if product_family:
                query = query.filter(MasterProduct.product_family == product_family)
            if status:
                query = query.filter(MasterProduct.status == status)

            rows = query.order_by(MasterProduct.master_product_id.asc()).limit(max(1, min(limit, 1000))).all()
            return {
                "status": "OK",
                "version": BusinessRegistryService.version,
                "count": len(rows),
                "master_products": [BusinessRegistryService._master_product_to_dict(row) for row in rows],
            }
        finally:
            db.close()

    @staticmethod
    def get_master_product(master_product_id: str) -> dict[str, Any]:
        db = SessionLocal()
        try:
            row = db.query(MasterProduct).filter(MasterProduct.master_product_id == master_product_id).first()
            if not row:
                return {"status": "NOT_FOUND", "version": BusinessRegistryService.version, "master_product_id": master_product_id}

            channels = (
                db.query(ProductChannel)
                .filter(ProductChannel.master_product_id == master_product_id)
                .order_by(ProductChannel.channel.asc())
                .all()
            )
            events = (
                db.query(BusinessEvent)
                .filter(BusinessEvent.master_product_id == master_product_id)
                .order_by(BusinessEvent.occurred_at.desc())
                .limit(25)
                .all()
            )
            return {
                "status": "OK",
                "version": BusinessRegistryService.version,
                "master_product": BusinessRegistryService._master_product_to_dict(row),
                "channels": [BusinessRegistryService._channel_to_dict(ch) for ch in channels],
                "recent_events": [BusinessRegistryService._event_to_dict(ev) for ev in events],
            }
        finally:
            db.close()

    @staticmethod
    def list_channels(
        master_product_id: str | None = None,
        channel: str | None = None,
        status: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        db = SessionLocal()
        try:
            query = db.query(ProductChannel)
            if master_product_id:
                query = query.filter(ProductChannel.master_product_id == master_product_id)
            if channel:
                query = query.filter(ProductChannel.channel == channel)
            if status:
                query = query.filter(ProductChannel.status == status)
            rows = query.order_by(ProductChannel.master_product_id.asc(), ProductChannel.channel.asc()).limit(max(1, min(limit, 2000))).all()
            return {
                "status": "OK",
                "version": BusinessRegistryService.version,
                "count": len(rows),
                "channels": [BusinessRegistryService._channel_to_dict(row) for row in rows],
            }
        finally:
            db.close()

    @staticmethod
    def resolve(
        sku: str | None = None,
        asin: str | None = None,
        channel: str | None = None,
        channel_product_id: str | None = None,
        channel_listing_id: str | None = None,
    ) -> dict[str, Any]:
        db = SessionLocal()
        try:
            candidates = []

            if sku:
                mp = db.query(MasterProduct).filter(MasterProduct.primary_sku == sku).first()
                if mp:
                    candidates.append(("master_product.primary_sku", mp.master_product_id))
                for ch in db.query(ProductChannel).filter(ProductChannel.sku == sku).all():
                    candidates.append(("product_channel.sku", ch.master_product_id))

            if asin:
                for ch in db.query(ProductChannel).filter(ProductChannel.asin == asin).all():
                    candidates.append(("product_channel.asin", ch.master_product_id))

            if channel_product_id:
                q = db.query(ProductChannel).filter(ProductChannel.channel_product_id == channel_product_id)
                if channel:
                    q = q.filter(ProductChannel.channel == channel)
                for ch in q.all():
                    candidates.append(("product_channel.channel_product_id", ch.master_product_id))

            if channel_listing_id:
                q = db.query(ProductChannel).filter(ProductChannel.channel_listing_id == channel_listing_id)
                if channel:
                    q = q.filter(ProductChannel.channel == channel)
                for ch in q.all():
                    candidates.append(("product_channel.channel_listing_id", ch.master_product_id))

            unique = []
            seen = set()
            for source, mpid in candidates:
                if mpid not in seen:
                    seen.add(mpid)
                    unique.append({"master_product_id": mpid, "matched_by": source})

            return {
                "status": "OK" if unique else "NOT_FOUND",
                "version": BusinessRegistryService.version,
                "matches": unique,
                "input": {
                    "sku": sku,
                    "asin": asin,
                    "channel": channel,
                    "channel_product_id": channel_product_id,
                    "channel_listing_id": channel_listing_id,
                },
            }
        finally:
            db.close()

    @staticmethod
    def create_event(
        event_type: str,
        title: str,
        master_product_id: str | None = None,
        channel: str | None = None,
        description: str | None = None,
        source: str | None = "swagger",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        db = SessionLocal()
        try:
            event = BusinessEvent(
                event_id=f"EV-{uuid4().hex[:12].upper()}",
                event_type=event_type,
                title=title,
                master_product_id=master_product_id,
                channel=channel,
                description=description,
                source=source,
                payload=payload or {},
            )
            db.add(event)
            db.commit()
            db.refresh(event)
            return {
                "status": "OK",
                "version": BusinessRegistryService.version,
                "event": BusinessRegistryService._event_to_dict(event),
            }
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": BusinessRegistryService.version, "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def events(master_product_id: str | None = None, event_type: str | None = None, limit: int = 100) -> dict[str, Any]:
        db = SessionLocal()
        try:
            query = db.query(BusinessEvent)
            if master_product_id:
                query = query.filter(BusinessEvent.master_product_id == master_product_id)
            if event_type:
                query = query.filter(BusinessEvent.event_type == event_type)
            rows = query.order_by(BusinessEvent.occurred_at.desc()).limit(max(1, min(limit, 1000))).all()
            return {
                "status": "OK",
                "version": BusinessRegistryService.version,
                "count": len(rows),
                "events": [BusinessRegistryService._event_to_dict(row) for row in rows],
            }
        finally:
            db.close()

    @staticmethod
    def _default_channel_rows(row: dict[str, Any]) -> list[dict[str, Any]]:
        mpid = row["master_product_id"]
        base = {
            "master_product_id": mpid,
            "brand": row.get("brand"),
            "primary_sku": row.get("primary_sku"),
            "sku": row.get("primary_sku"),
            "raw": row,
            "updated_at": datetime.utcnow(),
        }
        return [
            {
                **base,
                "channel": "Amazon US",
                "marketplace": "amazon.com",
                "currency": "USD",
                "asin": row.get("amazon_us_asin") or None,
                "channel_product_id": row.get("amazon_us_asin") or None,
                "status": "Mapped" if row.get("amazon_us_asin") else "Needs Mapping",
            },
            {
                **base,
                "channel": "Amazon CA",
                "marketplace": "amazon.ca",
                "currency": "CAD",
                "asin": row.get("amazon_ca_asin") or None,
                "channel_product_id": row.get("amazon_ca_asin") or None,
                "status": "Mapped" if row.get("amazon_ca_asin") else "Needs Mapping",
            },
            {
                **base,
                "channel": "Shopify",
                "marketplace": "shopify",
                "currency": "CAD",
                "channel_product_id": row.get("shopify_product_id") or None,
                "status": "Mapped" if row.get("shopify_product_id") else "Needs Mapping",
            },
            {
                **base,
                "channel": "Etsy",
                "marketplace": "etsy",
                "currency": "CAD",
                "channel_listing_id": row.get("etsy_listing_id") or None,
                "status": "Mapped" if row.get("etsy_listing_id") else "Needs Mapping",
            },
        ]

    @staticmethod
    def _master_product_to_dict(row: MasterProduct) -> dict[str, Any]:
        return {
            "id": row.id,
            "master_product_id": row.master_product_id,
            "brand": row.brand,
            "product_family": row.product_family,
            "primary_sku": row.primary_sku,
            "ean_upc": row.ean_upc,
            "name": row.name,
            "status": row.status,
            "lifecycle_stage": row.lifecycle_stage,
            "primary_channel_strategy": row.primary_channel_strategy,
            "notes": row.notes,
            "source": row.source,
            "active": row.active,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def _channel_to_dict(row: ProductChannel) -> dict[str, Any]:
        return {
            "id": row.id,
            "master_product_id": row.master_product_id,
            "brand": row.brand,
            "primary_sku": row.primary_sku,
            "channel": row.channel,
            "marketplace": row.marketplace,
            "currency": row.currency,
            "channel_product_id": row.channel_product_id,
            "channel_listing_id": row.channel_listing_id,
            "asin": row.asin,
            "sku": row.sku,
            "status": row.status,
            "notes": row.notes,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def _event_to_dict(row: BusinessEvent) -> dict[str, Any]:
        return {
            "id": row.id,
            "event_id": row.event_id,
            "event_type": row.event_type,
            "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
            "master_product_id": row.master_product_id,
            "channel": row.channel,
            "title": row.title,
            "description": row.description,
            "source": row.source,
            "payload": row.payload,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
