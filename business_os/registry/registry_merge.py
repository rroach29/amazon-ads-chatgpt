"""Registry merge preview and approved merge actions.

Safety rules:
- Preview is read-only.
- Merge is explicit and requires approve=true.
- No MasterProduct rows are deleted.
- Duplicate product is archived/inactivated and annotated in raw metadata.
- Marketplace identities and core linked records are reassigned to keeper.
- A BusinessEvent audit trail is written for rollback/reference.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from database import SessionLocal
from business_registry.models import BusinessEvent, MasterProduct, ProductChannel, ProductScore
from business_os.mission_control.models import BusinessObjective, MissionControlDecision
from business_os.execution_framework.models import ExecutionPlan
from business_os.executive.genome.models import ProductGenome
from business_os.registry.registry_integrity import RegistryIntegrityService


class RegistryMergeService:
    version = "business-os-0.9.3-safe-merge-preview"

    @classmethod
    def preview(cls, keeper_master_product_id: str, duplicate_master_product_id: str) -> dict[str, Any]:
        db = SessionLocal()
        try:
            keeper, duplicate, error = cls._load_pair(db, keeper_master_product_id, duplicate_master_product_id)
            if error:
                return error
            return cls._preview_payload(db, keeper, duplicate)
        finally:
            db.close()

    @classmethod
    def merge(
        cls,
        keeper_master_product_id: str,
        duplicate_master_product_id: str,
        approve: bool = False,
        reason: str | None = None,
        allow_variation_family: bool = False,
    ) -> dict[str, Any]:
        if not approve:
            return {
                "status": "APPROVAL_REQUIRED",
                "version": cls.version,
                "message": "Merge requires approve=true. Run preview first and only approve exact duplicates you have reviewed.",
                "keeper_master_product_id": keeper_master_product_id,
                "duplicate_master_product_id": duplicate_master_product_id,
            }

        db = SessionLocal()
        try:
            keeper, duplicate, error = cls._load_pair(db, keeper_master_product_id, duplicate_master_product_id)
            if error:
                return error
            preview = cls._preview_payload(db, keeper, duplicate)
            if preview.get("candidate_type") == "variation_family" and not allow_variation_family:
                return {
                    "status": "BLOCKED_VARIATION_FAMILY",
                    "version": cls.version,
                    "message": "This looks like a variation-family relationship, not a safe duplicate merge. Pass allow_variation_family=true only after manual review.",
                    "preview": preview,
                }

            moved = cls._apply_merge(db, keeper, duplicate, preview, reason=reason)
            db.commit()
            return {"status": "MERGED", "version": cls.version, "message": "Duplicate product archived and linked records moved to keeper.", "merge_event_id": moved["event_id"], "keeper_master_product_id": keeper.master_product_id, "duplicate_master_product_id": duplicate.master_product_id, "moved": moved, "preview": preview}
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def _load_pair(db, keeper_id: str, duplicate_id: str):
        if not keeper_id or not duplicate_id:
            return None, None, {"status": "ERROR", "message": "Both keeper_master_product_id and duplicate_master_product_id are required."}
        if keeper_id == duplicate_id:
            return None, None, {"status": "ERROR", "message": "Keeper and duplicate cannot be the same product."}
        keeper = db.query(MasterProduct).filter(MasterProduct.master_product_id == keeper_id).first()
        duplicate = db.query(MasterProduct).filter(MasterProduct.master_product_id == duplicate_id).first()
        if not keeper:
            return None, None, {"status": "NOT_FOUND", "message": f"Keeper product not found: {keeper_id}"}
        if not duplicate:
            return None, None, {"status": "NOT_FOUND", "message": f"Duplicate product not found: {duplicate_id}"}
        return keeper, duplicate, None

    @classmethod
    def _preview_payload(cls, db, keeper: MasterProduct, duplicate: MasterProduct) -> dict[str, Any]:
        channels = db.query(ProductChannel).filter(ProductChannel.master_product_id == duplicate.master_product_id).all()
        keeper_channels = db.query(ProductChannel).filter(ProductChannel.master_product_id == keeper.master_product_id).all()
        conflict_rows = cls._channel_conflicts(channels, keeper_channels)
        score, reasons, candidate_type = RegistryIntegrityService._candidate_score(
            keeper,
            duplicate,
            {
                keeper.master_product_id: keeper_channels,
                duplicate.master_product_id: channels,
            },
        )
        linked_counts = cls._linked_counts(db, duplicate.master_product_id)
        return {
            "status": "OK",
            "version": cls.version,
            "read_only": True,
            "candidate_type": candidate_type,
            "confidence": score,
            "reasons": reasons,
            "safe_to_merge": candidate_type == "exact_duplicate" and score >= 98 and not conflict_rows,
            "warning": "Variation-family matches are not safe duplicate merges." if candidate_type == "variation_family" else None,
            "keeper": cls._product_payload(keeper),
            "duplicate": cls._product_payload(duplicate),
            "will_move": {
                "product_channels": [cls._channel_payload(row) for row in channels],
                "linked_record_counts": linked_counts,
            },
            "keeper_existing_channels": [cls._channel_payload(row) for row in keeper_channels],
            "conflicts": conflict_rows,
            "will_archive_duplicate": True,
            "will_delete_anything": False,
            "action_required": "Use POST /business-os/registry/integrity/merge with approve=true after review.",
        }

    @staticmethod
    def _linked_counts(db, duplicate_id: str) -> dict[str, int]:
        return {
            "product_channels": db.query(ProductChannel).filter(ProductChannel.master_product_id == duplicate_id).count(),
            "business_events": db.query(BusinessEvent).filter(BusinessEvent.master_product_id == duplicate_id).count(),
            "product_scores": db.query(ProductScore).filter(ProductScore.master_product_id == duplicate_id).count(),
            "product_genomes": db.query(ProductGenome).filter(ProductGenome.master_product_id == duplicate_id).count(),
            "mission_control_decisions": db.query(MissionControlDecision).filter(MissionControlDecision.master_product_id == duplicate_id).count(),
            "business_objectives": db.query(BusinessObjective).filter(BusinessObjective.master_product_id == duplicate_id).count(),
            "execution_plans": db.query(ExecutionPlan).filter(ExecutionPlan.master_product_id == duplicate_id).count(),
        }

    @staticmethod
    def _channel_conflicts(duplicate_channels: list[ProductChannel], keeper_channels: list[ProductChannel]) -> list[dict[str, Any]]:
        conflicts = []
        keeper_keys = {(c.channel, c.marketplace, c.asin, c.sku): c for c in keeper_channels}
        keeper_marketplace_asins = {(c.channel, c.marketplace, c.asin): c for c in keeper_channels if c.asin}
        keeper_marketplace_skus = {(c.channel, c.marketplace, c.sku): c for c in keeper_channels if c.sku}
        for channel in duplicate_channels:
            exact_key = (channel.channel, channel.marketplace, channel.asin, channel.sku)
            if exact_key in keeper_keys:
                conflicts.append({"type": "exact_channel_duplicate", "duplicate_channel": RegistryMergeService._channel_payload(channel), "keeper_channel": RegistryMergeService._channel_payload(keeper_keys[exact_key])})
                continue
            asin_key = (channel.channel, channel.marketplace, channel.asin)
            if channel.asin and asin_key in keeper_marketplace_asins:
                conflicts.append({"type": "same_marketplace_asin", "duplicate_channel": RegistryMergeService._channel_payload(channel), "keeper_channel": RegistryMergeService._channel_payload(keeper_marketplace_asins[asin_key])})
            sku_key = (channel.channel, channel.marketplace, channel.sku)
            if channel.sku and sku_key in keeper_marketplace_skus:
                conflicts.append({"type": "same_marketplace_sku", "duplicate_channel": RegistryMergeService._channel_payload(channel), "keeper_channel": RegistryMergeService._channel_payload(keeper_marketplace_skus[sku_key])})
        return conflicts

    @classmethod
    def _apply_merge(cls, db, keeper: MasterProduct, duplicate: MasterProduct, preview: dict[str, Any], reason: str | None) -> dict[str, Any]:
        now = datetime.utcnow()
        event_id = f"EV-{uuid4().hex[:12].upper()}"
        moved_counts = cls._linked_counts(db, duplicate.master_product_id)

        # Reassign primary linked records.
        db.query(ProductChannel).filter(ProductChannel.master_product_id == duplicate.master_product_id).update({ProductChannel.master_product_id: keeper.master_product_id}, synchronize_session=False)
        db.query(BusinessEvent).filter(BusinessEvent.master_product_id == duplicate.master_product_id).update({BusinessEvent.master_product_id: keeper.master_product_id}, synchronize_session=False)
        db.query(ProductScore).filter(ProductScore.master_product_id == duplicate.master_product_id).update({ProductScore.master_product_id: keeper.master_product_id}, synchronize_session=False)
        db.query(MissionControlDecision).filter(MissionControlDecision.master_product_id == duplicate.master_product_id).update({MissionControlDecision.master_product_id: keeper.master_product_id, MissionControlDecision.product_name: keeper.name}, synchronize_session=False)
        db.query(BusinessObjective).filter(BusinessObjective.master_product_id == duplicate.master_product_id).update({BusinessObjective.master_product_id: keeper.master_product_id}, synchronize_session=False)
        db.query(ExecutionPlan).filter(ExecutionPlan.master_product_id == duplicate.master_product_id).update({ExecutionPlan.master_product_id: keeper.master_product_id, ExecutionPlan.product_name: keeper.name}, synchronize_session=False)

        # ProductGenome has unique master_product_id. Preserve keeper genome if it exists; otherwise move duplicate genome.
        keeper_genome = db.query(ProductGenome).filter(ProductGenome.master_product_id == keeper.master_product_id).first()
        duplicate_genome = db.query(ProductGenome).filter(ProductGenome.master_product_id == duplicate.master_product_id).first()
        if duplicate_genome and not keeper_genome:
            duplicate_genome.master_product_id = keeper.master_product_id
            duplicate_genome.name = keeper.name
            duplicate_genome.updated_at = now
        elif duplicate_genome and keeper_genome:
            raw_note = keeper_genome.evidence if isinstance(keeper_genome.evidence, dict) else {}
            raw_note.setdefault("merged_duplicate_genomes", []).append({"from_master_product_id": duplicate.master_product_id, "merged_at": now.isoformat(), "duplicate_genome_id": duplicate_genome.id})
            keeper_genome.evidence = raw_note

        original_raw = duplicate.raw if isinstance(duplicate.raw, dict) else {}
        duplicate.raw = {**original_raw, "merged_into": keeper.master_product_id, "merged_at": now.isoformat(), "merge_event_id": event_id, "merge_reason": reason, "merge_preview": {"confidence": preview.get("confidence"), "candidate_type": preview.get("candidate_type"), "reasons": preview.get("reasons")}}
        duplicate.status = "Merged"
        duplicate.lifecycle_stage = "Archived"
        duplicate.active = False
        duplicate.updated_at = now

        keeper_raw = keeper.raw if isinstance(keeper.raw, dict) else {}
        keeper_raw.setdefault("merged_products", []).append({"duplicate_master_product_id": duplicate.master_product_id, "merged_at": now.isoformat(), "event_id": event_id})
        keeper.raw = keeper_raw
        keeper.updated_at = now

        db.add(BusinessEvent(
            event_id=event_id,
            event_type="RegistryMerge",
            master_product_id=keeper.master_product_id,
            channel="Registry",
            title=f"Merged duplicate product {duplicate.master_product_id} into {keeper.master_product_id}",
            description=reason or "Approved registry merge.",
            source="registry_merge_service",
            payload={"keeper_master_product_id": keeper.master_product_id, "duplicate_master_product_id": duplicate.master_product_id, "moved_counts": moved_counts, "preview": preview, "rollback_note": "Duplicate was archived, not deleted. ProductChannel and linked IDs were moved to keeper."},
        ))
        return {"event_id": event_id, "moved_counts": moved_counts, "archived_duplicate": True}

    @staticmethod
    def _product_payload(product: MasterProduct) -> dict[str, Any]:
        return {"master_product_id": product.master_product_id, "name": product.name, "brand": product.brand, "product_family": product.product_family, "primary_sku": product.primary_sku, "status": product.status, "lifecycle_stage": product.lifecycle_stage, "source": product.source, "active": product.active}

    @staticmethod
    def _channel_payload(channel: ProductChannel) -> dict[str, Any]:
        return {"id": channel.id, "master_product_id": channel.master_product_id, "channel": channel.channel, "marketplace": channel.marketplace, "asin": channel.asin, "sku": channel.sku, "status": channel.status}
