"""Business Registry v1.3 — Registry Manager service.

Adds safe CRUD-style registry management without SQL.

Important design decision:
- Products are archived by default instead of hard-deleted.
- Historical sales/ad/decision data can remain attached to the Master Product ID.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func

from database import SessionLocal
from business_registry.models import BusinessEvent, MasterProduct, ProductChannel
from business_os.registry.manager.schemas import (
    ChannelMappingCreate,
    ChannelMappingUpdate,
    MasterProductCreate,
    MasterProductUpdate,
)


class RegistryManagerService:
    version = "business-registry-1.3"

    @classmethod
    def create_master_product(cls, payload: MasterProductCreate) -> dict[str, Any]:
        db = SessionLocal()
        try:
            mpid = cls._next_master_product_id(db)
            product = MasterProduct(
                master_product_id=mpid,
                brand=payload.brand,
                product_family=payload.product_family,
                primary_sku=payload.primary_sku,
                ean_upc=payload.ean_upc,
                name=payload.name,
                status=payload.status,
                lifecycle_stage=payload.lifecycle_stage,
                primary_channel_strategy=payload.primary_channel_strategy,
                notes=payload.notes,
                source="registry_manager",
                active=True,
                raw=payload.model_dump(),
            )
            db.add(product)
            cls._event(
                db,
                event_type="MasterProductCreated",
                title=f"Master Product created: {payload.name}",
                master_product_id=mpid,
                payload=payload.model_dump(),
            )
            db.commit()
            db.refresh(product)
            return {"status": "OK", "version": cls.version, "master_product": cls._product(product)}
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @classmethod
    def update_master_product(cls, master_product_id: str, payload: MasterProductUpdate) -> dict[str, Any]:
        db = SessionLocal()
        try:
            product = db.query(MasterProduct).filter(MasterProduct.master_product_id == master_product_id).first()
            if not product:
                return {"status": "NOT_FOUND", "version": cls.version, "master_product_id": master_product_id}

            changes = payload.model_dump(exclude_unset=True)
            for key, value in changes.items():
                setattr(product, key, value)
            product.updated_at = datetime.utcnow()

            cls._event(
                db,
                event_type="MasterProductUpdated",
                title=f"Master Product updated: {product.name}",
                master_product_id=master_product_id,
                payload=changes,
            )
            db.commit()
            db.refresh(product)
            return {"status": "OK", "version": cls.version, "master_product": cls._product(product), "changes": changes}
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @classmethod
    def archive_master_product(cls, master_product_id: str, reason: str | None = None) -> dict[str, Any]:
        db = SessionLocal()
        try:
            product = db.query(MasterProduct).filter(MasterProduct.master_product_id == master_product_id).first()
            if not product:
                return {"status": "NOT_FOUND", "version": cls.version, "master_product_id": master_product_id}

            product.active = False
            product.status = "Retired"
            product.updated_at = datetime.utcnow()

            cls._event(
                db,
                event_type="MasterProductArchived",
                title=f"Master Product archived: {product.name}",
                master_product_id=master_product_id,
                payload={"reason": reason},
            )
            db.commit()
            return {
                "status": "OK",
                "version": cls.version,
                "message": "Master Product archived. Historical data remains preserved.",
                "master_product": cls._product(product),
            }
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @classmethod
    def create_channel_mapping(cls, payload: ChannelMappingCreate) -> dict[str, Any]:
        db = SessionLocal()
        try:
            product = db.query(MasterProduct).filter(MasterProduct.master_product_id == payload.master_product_id).first()
            if not product:
                return {"status": "NOT_FOUND", "version": cls.version, "message": "Master Product not found", "master_product_id": payload.master_product_id}

            mapping = ProductChannel(
                master_product_id=payload.master_product_id,
                brand=payload.brand or product.brand,
                primary_sku=payload.primary_sku or product.primary_sku,
                channel=payload.channel,
                marketplace=payload.marketplace,
                currency=payload.currency,
                channel_product_id=payload.channel_product_id,
                channel_listing_id=payload.channel_listing_id,
                asin=payload.asin,
                sku=payload.sku or product.primary_sku,
                status=payload.status,
                notes=payload.notes,
                raw=payload.raw or payload.model_dump(),
            )
            db.add(mapping)

            cls._event(
                db,
                event_type="ChannelMappingCreated",
                title=f"Channel mapping created for {payload.master_product_id}: {payload.channel}",
                master_product_id=payload.master_product_id,
                channel=payload.channel,
                payload=payload.model_dump(),
            )
            db.commit()
            db.refresh(mapping)
            return {"status": "OK", "version": cls.version, "channel_mapping": cls._channel(mapping)}
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @classmethod
    def update_channel_mapping(cls, mapping_id: int, payload: ChannelMappingUpdate) -> dict[str, Any]:
        db = SessionLocal()
        try:
            mapping = db.query(ProductChannel).filter(ProductChannel.id == mapping_id).first()
            if not mapping:
                return {"status": "NOT_FOUND", "version": cls.version, "mapping_id": mapping_id}

            changes = payload.model_dump(exclude_unset=True)
            for key, value in changes.items():
                setattr(mapping, key, value)
            mapping.updated_at = datetime.utcnow()

            # Automatically mark mapped when identifiers exist.
            if any([mapping.asin, mapping.channel_product_id, mapping.channel_listing_id]):
                if not mapping.status or mapping.status == "Needs Mapping":
                    mapping.status = "Mapped"

            cls._event(
                db,
                event_type="ChannelMappingUpdated",
                title=f"Channel mapping updated: {mapping.master_product_id} / {mapping.channel}",
                master_product_id=mapping.master_product_id,
                channel=mapping.channel,
                payload=changes,
            )
            db.commit()
            db.refresh(mapping)
            return {"status": "OK", "version": cls.version, "channel_mapping": cls._channel(mapping), "changes": changes}
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @classmethod
    def delete_channel_mapping(cls, mapping_id: int, hard_delete: bool = False) -> dict[str, Any]:
        db = SessionLocal()
        try:
            mapping = db.query(ProductChannel).filter(ProductChannel.id == mapping_id).first()
            if not mapping:
                return {"status": "NOT_FOUND", "version": cls.version, "mapping_id": mapping_id}

            mapping_dict = cls._channel(mapping)
            if hard_delete:
                db.delete(mapping)
                action = "deleted"
                event_type = "ChannelMappingDeleted"
            else:
                mapping.status = "Inactive"
                mapping.updated_at = datetime.utcnow()
                action = "marked inactive"
                event_type = "ChannelMappingArchived"

            cls._event(
                db,
                event_type=event_type,
                title=f"Channel mapping {action}: {mapping_dict.get('master_product_id')} / {mapping_dict.get('channel')}",
                master_product_id=mapping_dict.get("master_product_id"),
                channel=mapping_dict.get("channel"),
                payload={"mapping": mapping_dict, "hard_delete": hard_delete},
            )
            db.commit()
            return {"status": "OK", "version": cls.version, "message": f"Channel mapping {action}.", "mapping": mapping_dict}
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @classmethod
    def mapping_completeness(cls) -> dict[str, Any]:
        db = SessionLocal()
        try:
            total_products = db.query(MasterProduct).count()
            total_channels = db.query(ProductChannel).count()
            mapped_channels = (
                db.query(ProductChannel)
                .filter(
                    (ProductChannel.status == "Mapped")
                    | (ProductChannel.asin.isnot(None))
                    | (ProductChannel.channel_product_id.isnot(None))
                    | (ProductChannel.channel_listing_id.isnot(None))
                )
                .count()
            )

            channel_breakdown = []
            rows = (
                db.query(ProductChannel.channel, func.count(ProductChannel.id))
                .group_by(ProductChannel.channel)
                .all()
            )
            for channel, count in rows:
                mapped = (
                    db.query(ProductChannel)
                    .filter(ProductChannel.channel == channel)
                    .filter(
                        (ProductChannel.status == "Mapped")
                        | (ProductChannel.asin.isnot(None))
                        | (ProductChannel.channel_product_id.isnot(None))
                        | (ProductChannel.channel_listing_id.isnot(None))
                    )
                    .count()
                )
                channel_breakdown.append({
                    "channel": channel,
                    "rows": count,
                    "mapped": mapped,
                    "unmapped": count - mapped,
                    "mapped_pct": round(mapped / count, 4) if count else None,
                })

            return {
                "status": "OK",
                "version": cls.version,
                "total_master_products": total_products,
                "total_channel_rows": total_channels,
                "mapped_channel_rows": mapped_channels,
                "unmapped_channel_rows": total_channels - mapped_channels,
                "mapped_pct": round(mapped_channels / total_channels, 4) if total_channels else None,
                "channel_breakdown": channel_breakdown,
            }
        finally:
            db.close()

    @classmethod
    def find_products(cls, q: str | None = None, status: str | None = None, active: bool | None = None, limit: int = 100) -> dict[str, Any]:
        db = SessionLocal()
        try:
            query = db.query(MasterProduct)
            if q:
                like = f"%{q}%"
                query = query.filter(
                    (MasterProduct.name.ilike(like))
                    | (MasterProduct.primary_sku.ilike(like))
                    | (MasterProduct.master_product_id.ilike(like))
                    | (MasterProduct.brand.ilike(like))
                    | (MasterProduct.product_family.ilike(like))
                )
            if status:
                query = query.filter(MasterProduct.status == status)
            if active is not None:
                query = query.filter(MasterProduct.active == active)

            rows = query.order_by(MasterProduct.master_product_id.asc()).limit(max(1, min(limit, 1000))).all()
            return {"status": "OK", "version": cls.version, "count": len(rows), "master_products": [cls._product(row) for row in rows]}
        finally:
            db.close()

    @staticmethod
    def _next_master_product_id(db) -> str:
        rows = db.query(MasterProduct.master_product_id).all()
        max_num = 0
        for (mpid,) in rows:
            if not mpid or not str(mpid).startswith("MP-"):
                continue
            try:
                max_num = max(max_num, int(str(mpid).split("-")[1]))
            except Exception:
                continue
        return f"MP-{max_num + 1:05d}"

    @staticmethod
    def _event(db, event_type: str, title: str, master_product_id: str | None = None, channel: str | None = None, payload: dict[str, Any] | None = None):
        db.add(
            BusinessEvent(
                event_id=f"EV-{uuid4().hex[:12].upper()}",
                event_type=event_type,
                occurred_at=datetime.utcnow(),
                master_product_id=master_product_id,
                channel=channel,
                title=title,
                source="registry_manager",
                payload=payload or {},
            )
        )

    @staticmethod
    def _product(row: MasterProduct) -> dict[str, Any]:
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
            "active": row.active,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def _channel(row: ProductChannel) -> dict[str, Any]:
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
