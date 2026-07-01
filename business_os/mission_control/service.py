"""Business OS v0.3.0 — Mission Control service.

Mission Control turns existing Product Genome + Registry data into a ranked
decision queue. The engine is intentionally conservative: if the data is weak,
it creates data-quality decisions instead of pretending to know what to do.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import desc

from database import SessionLocal
from business_registry.models import BusinessEvent, MasterProduct, ProductChannel
from business_os.executive.genome.models import ProductGenome
from business_os.mission_control.models import BusinessObjective, MissionControlDecision


class MissionControlService:
    version = "business-os-0.3.0"

    @classmethod
    def summary(cls) -> dict[str, Any]:
        db = SessionLocal()
        try:
            pending = db.query(MissionControlDecision).filter(MissionControlDecision.status == "Pending").count()
            approved = db.query(MissionControlDecision).filter(MissionControlDecision.status == "Approved").count()
            dismissed = db.query(MissionControlDecision).filter(MissionControlDecision.status == "Dismissed").count()
            top = (
                db.query(MissionControlDecision)
                .filter(MissionControlDecision.status == "Pending")
                .order_by(desc(MissionControlDecision.urgency), desc(MissionControlDecision.estimated_monthly_impact))
                .limit(3)
                .all()
            )
            opportunity = sum(float(row.estimated_monthly_impact or 0) for row in top)
            return {
                "status": "OK",
                "version": cls.version,
                "pending_decisions": pending,
                "approved_decisions": approved,
                "dismissed_decisions": dismissed,
                "top_three_count": len(top),
                "top_three_estimated_monthly_impact": round(opportunity, 2),
                "top_three": [cls._decision(row) for row in top],
            }
        finally:
            db.close()

    @classmethod
    def generate(cls, limit: int = 250, replace_pending: bool = True) -> dict[str, Any]:
        db = SessionLocal()
        try:
            if replace_pending:
                db.query(MissionControlDecision).filter(MissionControlDecision.status == "Pending").delete()

            genomes = (
                db.query(ProductGenome)
                .order_by(ProductGenome.product_health.desc())
                .limit(max(1, min(limit, 1000)))
                .all()
            )

            created = []
            for genome in genomes:
                for candidate in cls._candidates_for_genome(db, genome):
                    decision = MissionControlDecision(**candidate)
                    db.add(decision)
                    created.append(decision)

            if not created:
                candidate = cls._fallback_decision(db)
                decision = MissionControlDecision(**candidate)
                db.add(decision)
                created.append(decision)

            cls._record_event(
                db,
                "MissionControlGenerated",
                f"Mission Control generated {len(created)} decision candidates.",
                payload={"created": len(created), "replace_pending": replace_pending},
            )

            db.commit()
            for row in created:
                db.refresh(row)

            ranked = (
                db.query(MissionControlDecision)
                .filter(MissionControlDecision.status == "Pending")
                .order_by(desc(MissionControlDecision.urgency), desc(MissionControlDecision.estimated_monthly_impact))
                .limit(25)
                .all()
            )

            return {
                "status": "OK",
                "version": cls.version,
                "created_count": len(created),
                "pending_count": db.query(MissionControlDecision).filter(MissionControlDecision.status == "Pending").count(),
                "top_decisions": [cls._decision(row) for row in ranked],
            }
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @classmethod
    def list_decisions(cls, status: str = "Pending", limit: int = 100) -> dict[str, Any]:
        db = SessionLocal()
        try:
            query = db.query(MissionControlDecision)
            if status:
                query = query.filter(MissionControlDecision.status == status)
            rows = (
                query.order_by(desc(MissionControlDecision.urgency), desc(MissionControlDecision.estimated_monthly_impact))
                .limit(max(1, min(limit, 500)))
                .all()
            )
            return {"status": "OK", "version": cls.version, "count": len(rows), "decisions": [cls._decision(row) for row in rows]}
        finally:
            db.close()

    @classmethod
    def get_decision(cls, decision_id: str) -> dict[str, Any]:
        db = SessionLocal()
        try:
            row = db.query(MissionControlDecision).filter(MissionControlDecision.decision_id == decision_id).first()
            if not row:
                return {"status": "NOT_FOUND", "version": cls.version, "decision_id": decision_id}
            return {"status": "OK", "version": cls.version, "decision": cls._decision(row)}
        finally:
            db.close()

    @classmethod
    def approve(cls, decision_id: str) -> dict[str, Any]:
        return cls._transition(decision_id, "Approved", approved=True)

    @classmethod
    def dismiss(cls, decision_id: str) -> dict[str, Any]:
        return cls._transition(decision_id, "Dismissed", dismissed=True)

    @classmethod
    def defer(cls, decision_id: str) -> dict[str, Any]:
        return cls._transition(decision_id, "Deferred")

    @classmethod
    def simulate(cls, decision_id: str) -> dict[str, Any]:
        db = SessionLocal()
        try:
            row = db.query(MissionControlDecision).filter(MissionControlDecision.decision_id == decision_id).first()
            if not row:
                return {"status": "NOT_FOUND", "version": cls.version, "decision_id": decision_id}

            impact = float(row.estimated_monthly_impact or 0)
            confidence = int(row.confidence or 50)
            downside = round(max(impact * 0.35, 0), 2)
            upside = round(impact * 1.25, 2)

            return {
                "status": "OK",
                "version": cls.version,
                "decision_id": decision_id,
                "simulation": {
                    "title": row.title,
                    "expected_monthly_impact": round(impact, 2),
                    "optimistic_monthly_impact": upside,
                    "downside_risk": downside,
                    "confidence": confidence,
                    "reversibility": row.reversibility,
                    "interpretation": cls._simulation_text(row, impact, confidence),
                },
            }
        finally:
            db.close()

    @classmethod
    def explain(cls, decision_id: str) -> dict[str, Any]:
        db = SessionLocal()
        try:
            row = db.query(MissionControlDecision).filter(MissionControlDecision.decision_id == decision_id).first()
            if not row:
                return {"status": "NOT_FOUND", "version": cls.version, "decision_id": decision_id}
            return {
                "status": "OK",
                "version": cls.version,
                "decision_id": decision_id,
                "explanation": {
                    "title": row.title,
                    "reason": row.reason,
                    "why_now": row.why_now,
                    "if_you_do": row.if_you_do,
                    "if_you_do_not": row.if_you_do_not,
                    "evidence": row.evidence or [],
                    "confidence": row.confidence,
                    "reversibility": row.reversibility,
                },
            }
        finally:
            db.close()

    @classmethod
    def objectives(cls, master_product_id: str | None = None) -> dict[str, Any]:
        db = SessionLocal()
        try:
            query = db.query(BusinessObjective)
            if master_product_id:
                query = query.filter(BusinessObjective.master_product_id == master_product_id)
            rows = query.order_by(BusinessObjective.created_at.desc()).limit(250).all()
            return {"status": "OK", "version": cls.version, "count": len(rows), "objectives": [cls._objective(row) for row in rows]}
        finally:
            db.close()

    @classmethod
    def create_objective(
        cls,
        title: str,
        objective_type: str = "Maximize Profit",
        portfolio_strategy: str = "Grow",
        scope: str = "business",
        master_product_id: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        db = SessionLocal()
        try:
            objective = BusinessObjective(
                objective_id=f"OBJ-{uuid4().hex[:10].upper()}",
                scope=scope,
                master_product_id=master_product_id,
                title=title,
                objective_type=objective_type,
                portfolio_strategy=portfolio_strategy,
                notes=notes,
                payload={
                    "title": title,
                    "objective_type": objective_type,
                    "portfolio_strategy": portfolio_strategy,
                    "scope": scope,
                    "master_product_id": master_product_id,
                },
            )
            db.add(objective)
            cls._record_event(
                db,
                "BusinessObjectiveCreated",
                f"Business Objective created: {title}",
                master_product_id=master_product_id,
                payload=objective.payload,
            )
            db.commit()
            db.refresh(objective)
            return {"status": "OK", "version": cls.version, "objective": cls._objective(objective)}
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @classmethod
    def _transition(cls, decision_id: str, status: str, approved: bool = False, dismissed: bool = False) -> dict[str, Any]:
        db = SessionLocal()
        try:
            row = db.query(MissionControlDecision).filter(MissionControlDecision.decision_id == decision_id).first()
            if not row:
                return {"status": "NOT_FOUND", "version": cls.version, "decision_id": decision_id}

            row.status = status
            row.updated_at = datetime.utcnow()
            if approved:
                row.approved = True
                row.approved_at = datetime.utcnow()
            if dismissed:
                row.dismissed_at = datetime.utcnow()

            cls._record_event(
                db,
                f"Decision{status}",
                f"Decision {status.lower()}: {row.title}",
                master_product_id=row.master_product_id,
                payload={"decision_id": decision_id, "status": status, "title": row.title},
            )
            db.commit()
            db.refresh(row)
            return {"status": "OK", "version": cls.version, "decision": cls._decision(row)}
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @classmethod
    def _candidates_for_genome(cls, db, genome: ProductGenome) -> list[dict[str, Any]]:
        candidates = []

        product = db.query(MasterProduct).filter(MasterProduct.master_product_id == genome.master_product_id).first()
        channels = db.query(ProductChannel).filter(ProductChannel.master_product_id == genome.master_product_id).all()
        mapped_channels = [
            c for c in channels
            if c.status == "Mapped" or c.asin or c.channel_product_id or c.channel_listing_id
        ]

        # 1. Data quality / mapping work. This is often the highest-value early action.
        if channels and len(mapped_channels) == 0:
            candidates.append(cls._candidate(
                genome=genome,
                title=f"Complete channel mappings for {genome.name}",
                category="Registry",
                priority="HIGH",
                estimated_impact=125,
                confidence=92,
                reversibility="High",
                urgency=94,
                recommendation="Add the missing Amazon/Shopify/Etsy identifiers so Business OS can connect this product to real sales and advertising data.",
                reason="This product exists in the Master Product Registry but none of its channel rows are mapped.",
                why_now="Product Genome accuracy is limited until the product can be linked to channel data.",
                if_you_do="Future reports, Product Genome scores, and Mission Control recommendations will become more accurate.",
                if_you_do_not="The Executive Brain may continue treating this product as unknown or low-confidence.",
                evidence=[{"signal": "mapped_channel_count", "value": len(mapped_channels)}, {"signal": "channel_count", "value": len(channels)}],
            ))

        # 2. High advertising dependency.
        if int(genome.advertising_dependency_index or 0) >= 70:
            candidates.append(cls._candidate(
                genome=genome,
                title=f"Review advertising dependency for {genome.name}",
                category="Advertising",
                priority="HIGH",
                estimated_impact=max(75, int(genome.advertising_dependency_index or 0) * 2),
                confidence=max(55, int(genome.confidence or 50)),
                reversibility="High",
                urgency=min(96, int(genome.advertising_dependency_index or 0) + 15),
                recommendation="Review spend, bids, and conversion quality before increasing advertising.",
                reason="The Product Genome shows high Advertising Dependency.",
                why_now="High dependency can hide products that only sell while paid traffic is active.",
                if_you_do="You may reduce wasted spend or identify the listing/conversion work needed before scaling.",
                if_you_do_not="The product may continue consuming ad budget without building sustainable demand.",
                evidence=[
                    {"signal": "advertising_dependency_index", "value": genome.advertising_dependency_index},
                    {"signal": "confidence", "value": genome.confidence},
                ],
            ))

        # 3. Organic candidate.
        if int(genome.organic_strength or 0) >= 80 and int(genome.advertising_dependency_index or 100) <= 40:
            candidates.append(cls._candidate(
                genome=genome,
                title=f"Test ad-spend reduction for {genome.name}",
                category="Profit",
                priority="MEDIUM",
                estimated_impact=max(50, 100 - int(genome.advertising_dependency_index or 0)),
                confidence=max(60, int(genome.confidence or 50)),
                reversibility="High",
                urgency=72,
                recommendation="Consider a small controlled bid/spend reduction test.",
                reason="Organic Strength is high while Advertising Dependency is relatively low.",
                why_now="This product may be able to keep sales while using less paid traffic.",
                if_you_do="Profit may improve if paid clicks are being replaced by organic demand.",
                if_you_do_not="You may continue paying for sales that would have happened organically.",
                evidence=[
                    {"signal": "organic_strength", "value": genome.organic_strength},
                    {"signal": "advertising_dependency_index", "value": genome.advertising_dependency_index},
                ],
            ))

        # 4. Low confidence.
        if int(genome.confidence or 0) < 60:
            candidates.append(cls._candidate(
                genome=genome,
                title=f"Improve data confidence for {genome.name}",
                category="Data Quality",
                priority="MEDIUM",
                estimated_impact=60,
                confidence=90,
                reversibility="High",
                urgency=65,
                recommendation="Improve linked data before making aggressive business decisions for this product.",
                reason="Product Genome confidence is low.",
                why_now="Low confidence means the Executive Brain may not have enough evidence to recommend operational changes.",
                if_you_do="Recommendations for this product will become safer and more useful.",
                if_you_do_not="The product may remain excluded from high-quality Mission Control decisions.",
                evidence=[{"signal": "confidence", "value": genome.confidence}],
            ))

        return candidates

    @classmethod
    def _fallback_decision(cls, db) -> dict[str, Any]:
        product_count = db.query(MasterProduct).count()
        genome_count = db.query(ProductGenome).count()
        return {
            "decision_id": f"DEC-{uuid4().hex[:12].upper()}",
            "master_product_id": None,
            "product_name": None,
            "title": "Generate Product Genomes and improve product mappings",
            "category": "Setup",
            "priority": "HIGH",
            "status": "Pending",
            "estimated_monthly_impact": 100,
            "confidence": 95,
            "reversibility": "High",
            "urgency": 90,
            "recommendation": "Recalculate Product Genomes and complete missing channel mappings.",
            "reason": "Mission Control needs Product Genomes and mapped channels to generate product-specific recommendations.",
            "why_now": "This is the foundation for useful daily executive decisions.",
            "if_you_do": "Business OS will produce more specific, product-level decisions.",
            "if_you_do_not": "Mission Control will remain limited to generic setup guidance.",
            "evidence": [{"signal": "master_products", "value": product_count}, {"signal": "product_genomes", "value": genome_count}],
            "actions": cls._actions(),
            "payload": {"fallback": True},
        }

    @classmethod
    def _candidate(
        cls,
        genome: ProductGenome,
        title: str,
        category: str,
        priority: str,
        estimated_impact: float,
        confidence: int,
        reversibility: str,
        urgency: int,
        recommendation: str,
        reason: str,
        why_now: str,
        if_you_do: str,
        if_you_do_not: str,
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "decision_id": f"DEC-{uuid4().hex[:12].upper()}",
            "master_product_id": genome.master_product_id,
            "product_name": genome.name,
            "title": title,
            "category": category,
            "priority": priority,
            "status": "Pending",
            "estimated_monthly_impact": float(estimated_impact),
            "confidence": int(confidence),
            "reversibility": reversibility,
            "urgency": int(urgency),
            "recommendation": recommendation,
            "reason": reason,
            "why_now": why_now,
            "if_you_do": if_you_do,
            "if_you_do_not": if_you_do_not,
            "evidence": evidence,
            "actions": cls._actions(),
            "payload": {"score_version": genome.score_version},
        }

    @staticmethod
    def _actions() -> list[dict[str, str]]:
        return [
            {"id": "approve", "label": "Approve"},
            {"id": "simulate", "label": "Simulate"},
            {"id": "explain", "label": "Explain"},
            {"id": "defer", "label": "Defer"},
            {"id": "dismiss", "label": "Dismiss"},
        ]

    @staticmethod
    def _simulation_text(row: MissionControlDecision, impact: float, confidence: int) -> str:
        if impact <= 0:
            return "This decision is primarily about data quality or risk reduction, not immediate measured profit."
        if confidence >= 80:
            return "This action has strong supporting evidence and appears easy to test."
        return "This action may be useful, but confidence is moderate. Treat it as a controlled experiment."

    @staticmethod
    def _record_event(db, event_type: str, title: str, master_product_id: str | None = None, payload: dict[str, Any] | None = None):
        db.add(BusinessEvent(
            event_id=f"EV-{uuid4().hex[:12].upper()}",
            event_type=event_type,
            occurred_at=datetime.utcnow(),
            master_product_id=master_product_id,
            title=title,
            source="mission_control",
            payload=payload or {},
        ))

    @staticmethod
    def _decision(row: MissionControlDecision) -> dict[str, Any]:
        return {
            "id": row.id,
            "decision_id": row.decision_id,
            "master_product_id": row.master_product_id,
            "product_name": row.product_name,
            "title": row.title,
            "category": row.category,
            "priority": row.priority,
            "status": row.status,
            "estimated_monthly_impact": row.estimated_monthly_impact,
            "confidence": row.confidence,
            "reversibility": row.reversibility,
            "urgency": row.urgency,
            "recommendation": row.recommendation,
            "reason": row.reason,
            "why_now": row.why_now,
            "if_you_do": row.if_you_do,
            "if_you_do_not": row.if_you_do_not,
            "evidence": row.evidence,
            "actions": row.actions,
            "approved": row.approved,
            "approved_at": row.approved_at.isoformat() if row.approved_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def _objective(row: BusinessObjective) -> dict[str, Any]:
        return {
            "id": row.id,
            "objective_id": row.objective_id,
            "scope": row.scope,
            "master_product_id": row.master_product_id,
            "title": row.title,
            "objective_type": row.objective_type,
            "portfolio_strategy": row.portfolio_strategy,
            "status": row.status,
            "target_metric": row.target_metric,
            "target_value": row.target_value,
            "current_value": row.current_value,
            "notes": row.notes,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
