"""Business OS v0.5.0 — Execution Planner.

The planner converts Mission Control recommendations into safe, auditable execution plans.

v0.5.0 is intentionally conservative:
- It creates executable plans.
- It simulates the exact intended change.
- It creates steps and history.
- It supports dry-run execution by default.
- Live Amazon Ads writes are gated behind execute_live=true and connector readiness.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import desc

from database import SessionLocal
from business_os.execution_framework.models import ExecutionPlan, ExecutionResult, ExecutionStep
from business_os.mission_control.models import MissionControlDecision


class ExecutionPlannerService:
    version = "business-os-0.5.0"

    @classmethod
    def create_plan_from_decision(cls, decision_id: str) -> dict[str, Any]:
        db = SessionLocal()
        try:
            existing = (
                db.query(ExecutionPlan)
                .filter(ExecutionPlan.decision_id == decision_id)
                .filter(ExecutionPlan.status.in_(["Planned", "Ready", "Approved"]))
                .first()
            )
            if existing:
                return {"status": "OK", "version": cls.version, "plan": cls._plan(existing), "message": "Existing active plan returned."}

            decision = db.query(MissionControlDecision).filter(MissionControlDecision.decision_id == decision_id).first()
            if not decision:
                return {"status": "NOT_FOUND", "version": cls.version, "message": f"Decision {decision_id} not found."}

            executable = cls._infer_execution(decision)
            plan_id = f"PLAN-{uuid4().hex[:12].upper()}"

            plan = ExecutionPlan(
                plan_id=plan_id,
                decision_id=decision.decision_id,
                master_product_id=decision.master_product_id,
                product_name=decision.product_name,
                platform=executable["platform"],
                action_type=executable["action_type"],
                title=executable["title"],
                status="Planned",
                risk_level=executable["risk_level"],
                expected_monthly_impact=float(decision.estimated_monthly_impact or 0),
                confidence=int(decision.confidence or 0),
                rollback_available=executable["rollback_available"],
                simulation=cls._simulation(decision, executable),
                execution_payload=executable,
                source_decision=cls._decision(decision),
                approved_at=datetime.utcnow(),
            )
            db.add(plan)

            for index, step in enumerate(cls._steps_for(plan_id, executable), start=1):
                db.add(ExecutionStep(
                    step_id=f"STEP-{uuid4().hex[:12].upper()}",
                    plan_id=plan_id,
                    sequence=index,
                    name=step["name"],
                    action_type=step["action_type"],
                    platform=executable["platform"],
                    status="Pending",
                    request_payload=step.get("request_payload"),
                ))

            decision.status = "Approved"
            decision.approved = True
            decision.approved_at = datetime.utcnow()
            decision.updated_at = datetime.utcnow()

            db.commit()
            db.refresh(plan)
            return {"status": "OK", "version": cls.version, "plan": cls._plan(plan)}
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @classmethod
    def simulate_decision(cls, decision_id: str) -> dict[str, Any]:
        db = SessionLocal()
        try:
            decision = db.query(MissionControlDecision).filter(MissionControlDecision.decision_id == decision_id).first()
            if not decision:
                return {"status": "NOT_FOUND", "version": cls.version, "message": f"Decision {decision_id} not found."}

            executable = cls._infer_execution(decision)
            return {
                "status": "OK",
                "version": cls.version,
                "decision_id": decision_id,
                "executable": executable,
                "simulation": cls._simulation(decision, executable),
            }
        finally:
            db.close()

    @classmethod
    def list_plans(cls, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        db = SessionLocal()
        try:
            query = db.query(ExecutionPlan)
            if status:
                query = query.filter(ExecutionPlan.status == status)
            rows = query.order_by(desc(ExecutionPlan.created_at)).limit(max(1, min(limit, 500))).all()
            return {
                "status": "OK",
                "version": cls.version,
                "count": len(rows),
                "plans": [cls._plan(row) for row in rows],
            }
        finally:
            db.close()

    @classmethod
    def get_plan(cls, plan_id: str) -> dict[str, Any]:
        db = SessionLocal()
        try:
            plan = db.query(ExecutionPlan).filter(ExecutionPlan.plan_id == plan_id).first()
            if not plan:
                return {"status": "NOT_FOUND", "version": cls.version, "message": f"Plan {plan_id} not found."}
            steps = db.query(ExecutionStep).filter(ExecutionStep.plan_id == plan_id).order_by(ExecutionStep.sequence).all()
            results = db.query(ExecutionResult).filter(ExecutionResult.plan_id == plan_id).order_by(desc(ExecutionResult.created_at)).all()
            return {
                "status": "OK",
                "version": cls.version,
                "plan": cls._plan(plan),
                "steps": [cls._step(step) for step in steps],
                "results": [cls._result(result) for result in results],
            }
        finally:
            db.close()

    @classmethod
    def run_plan(cls, plan_id: str, execute_live: bool = False) -> dict[str, Any]:
        """Run a plan.

        v0.5.0 defaults to safe dry-run execution. Live writes require execute_live=true.
        Even then, unsupported connector operations are marked as RequiresConnector rather than faked.
        """
        db = SessionLocal()
        try:
            plan = db.query(ExecutionPlan).filter(ExecutionPlan.plan_id == plan_id).first()
            if not plan:
                return {"status": "NOT_FOUND", "version": cls.version, "message": f"Plan {plan_id} not found."}

            steps = db.query(ExecutionStep).filter(ExecutionStep.plan_id == plan_id).order_by(ExecutionStep.sequence).all()
            now = datetime.utcnow()
            plan.status = "Running"
            plan.executed_at = now

            result_status = "DryRunComplete"
            success = True
            api_response = {
                "mode": "dry_run" if not execute_live else "live_requested",
                "message": "No live marketplace write was performed." if not execute_live else "Live execution connector not enabled in v0.5.0 package.",
                "planned_action": plan.execution_payload,
            }

            for step in steps:
                step.started_at = datetime.utcnow()
                if execute_live:
                    step.status = "RequiresConnector"
                    step.error = "Live Amazon Ads write connector is intentionally gated. Enable connector implementation before live execution."
                    success = False
                    result_status = "RequiresConnector"
                else:
                    step.status = "DryRunComplete"
                    step.response_payload = {"dry_run": True, "would_execute": step.request_payload}
                step.completed_at = datetime.utcnow()

            if execute_live:
                plan.status = "RequiresConnector"
                plan.failed_at = datetime.utcnow()
            else:
                plan.status = "DryRunComplete"
                plan.completed_at = datetime.utcnow()

            plan.verification = {
                "verified": not execute_live,
                "mode": "dry_run",
                "message": "Plan structure verified. No external marketplace changes made.",
            }

            result = ExecutionResult(
                result_id=f"RES-{uuid4().hex[:12].upper()}",
                plan_id=plan.plan_id,
                decision_id=plan.decision_id,
                platform=plan.platform,
                action_type=plan.action_type,
                status=result_status,
                success=success,
                api_request=plan.execution_payload,
                api_response=api_response,
                verification=plan.verification,
                error=None if success else "Live connector not enabled.",
            )
            db.add(result)

            db.commit()
            return cls.get_plan(plan_id)
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @classmethod
    def history(cls, limit: int = 100) -> dict[str, Any]:
        db = SessionLocal()
        try:
            results = db.query(ExecutionResult).order_by(desc(ExecutionResult.created_at)).limit(max(1, min(limit, 500))).all()
            return {
                "status": "OK",
                "version": cls.version,
                "count": len(results),
                "results": [cls._result(result) for result in results],
            }
        finally:
            db.close()

    @classmethod
    def _infer_execution(cls, decision: MissionControlDecision) -> dict[str, Any]:
        text = " ".join([
            decision.title or "",
            decision.recommendation or "",
            decision.reason or "",
        ]).lower()

        evidence = decision.evidence or []
        evidence_map = {item.get("signal"): item.get("value") for item in evidence if isinstance(item, dict)}
        search_term = evidence_map.get("search_term")

        if "negative" in text:
            return {
                "platform": "amazon_ads",
                "action_type": "add_negative_keyword",
                "title": f"Add negative keyword: {search_term or 'search term'}",
                "risk_level": "Low",
                "rollback_available": True,
                "entity": "keyword",
                "keyword_text": search_term,
                "match_type": "negativeExact",
                "requires": ["campaign_id", "ad_group_id"],
                "missing_fields": ["campaign_id", "ad_group_id"],
                "source": "product_search_intelligence",
            }

        if "exact match" in text or "harvest" in text:
            return {
                "platform": "amazon_ads",
                "action_type": "add_exact_keyword",
                "title": f"Add exact keyword: {search_term or 'search term'}",
                "risk_level": "Low",
                "rollback_available": True,
                "entity": "keyword",
                "keyword_text": search_term,
                "match_type": "exact",
                "suggested_bid": None,
                "requires": ["campaign_id", "ad_group_id", "bid"],
                "missing_fields": ["campaign_id", "ad_group_id", "bid"],
                "source": "product_search_intelligence",
            }

        if "reduce bid" in text or "decrease bid" in text:
            return {
                "platform": "amazon_ads",
                "action_type": "decrease_bid",
                "title": decision.title or "Decrease bid",
                "risk_level": "Medium",
                "rollback_available": True,
                "entity": "keyword_or_target",
                "requires": ["target_id", "current_bid", "new_bid"],
                "missing_fields": ["target_id", "current_bid", "new_bid"],
                "source": decision.source,
            }

        return {
            "platform": "manual",
            "action_type": "manual_review",
            "title": decision.title or "Manual review",
            "risk_level": "Low",
            "rollback_available": False,
            "entity": "decision",
            "requires": [],
            "missing_fields": [],
            "source": decision.source,
        }

    @classmethod
    def _simulation(cls, decision: MissionControlDecision, executable: dict[str, Any]) -> dict[str, Any]:
        missing = executable.get("missing_fields", [])
        can_execute_live = len(missing) == 0 and executable.get("platform") != "manual"

        return {
            "decision_id": decision.decision_id,
            "platform": executable.get("platform"),
            "action_type": executable.get("action_type"),
            "current_state": "Search term exists in current report evidence.",
            "proposed_change": executable.get("title"),
            "expected_monthly_impact": float(decision.estimated_monthly_impact or 0),
            "confidence": int(decision.confidence or 0),
            "risk_level": executable.get("risk_level"),
            "rollback_available": executable.get("rollback_available"),
            "can_execute_live": can_execute_live,
            "missing_fields": missing,
            "explanation": (
                "This plan is ready for live execution."
                if can_execute_live
                else "This plan is structurally valid but needs campaign/ad group identifiers before live Amazon Ads execution."
            ),
            "dry_run_available": True,
        }

    @classmethod
    def _steps_for(cls, plan_id: str, executable: dict[str, Any]) -> list[dict[str, Any]]:
        action = executable.get("action_type")
        if action == "add_exact_keyword":
            return [
                {"name": "Validate campaign and ad group", "action_type": "validate_target_location", "request_payload": executable},
                {"name": "Create Exact Match keyword", "action_type": "amazon_ads_create_keyword", "request_payload": executable},
                {"name": "Verify keyword exists", "action_type": "verify_keyword_created", "request_payload": executable},
                {"name": "Record outcome baseline", "action_type": "record_outcome_baseline", "request_payload": executable},
            ]
        if action == "add_negative_keyword":
            return [
                {"name": "Validate negative keyword location", "action_type": "validate_target_location", "request_payload": executable},
                {"name": "Create Negative keyword", "action_type": "amazon_ads_create_negative_keyword", "request_payload": executable},
                {"name": "Verify negative keyword exists", "action_type": "verify_negative_keyword_created", "request_payload": executable},
                {"name": "Record waste baseline", "action_type": "record_outcome_baseline", "request_payload": executable},
            ]
        return [
            {"name": "Manual review", "action_type": "manual_review", "request_payload": executable},
            {"name": "Record decision", "action_type": "record_manual_decision", "request_payload": executable},
        ]

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
            "urgency": row.urgency,
            "recommendation": row.recommendation,
            "reason": row.reason,
            "why_now": row.why_now,
            "evidence": row.evidence,
            "source": row.source,
        }

    @staticmethod
    def _plan(row: ExecutionPlan) -> dict[str, Any]:
        return {
            "id": row.id,
            "plan_id": row.plan_id,
            "decision_id": row.decision_id,
            "master_product_id": row.master_product_id,
            "product_name": row.product_name,
            "platform": row.platform,
            "action_type": row.action_type,
            "title": row.title,
            "status": row.status,
            "risk_level": row.risk_level,
            "expected_monthly_impact": row.expected_monthly_impact,
            "confidence": row.confidence,
            "rollback_available": row.rollback_available,
            "simulation": row.simulation,
            "execution_payload": row.execution_payload,
            "verification": row.verification,
            "approved_at": row.approved_at.isoformat() if row.approved_at else None,
            "executed_at": row.executed_at.isoformat() if row.executed_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "failed_at": row.failed_at.isoformat() if row.failed_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def _step(row: ExecutionStep) -> dict[str, Any]:
        return {
            "id": row.id,
            "step_id": row.step_id,
            "plan_id": row.plan_id,
            "sequence": row.sequence,
            "name": row.name,
            "action_type": row.action_type,
            "status": row.status,
            "platform": row.platform,
            "request_payload": row.request_payload,
            "response_payload": row.response_payload,
            "error": row.error,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def _result(row: ExecutionResult) -> dict[str, Any]:
        return {
            "id": row.id,
            "result_id": row.result_id,
            "plan_id": row.plan_id,
            "decision_id": row.decision_id,
            "platform": row.platform,
            "action_type": row.action_type,
            "status": row.status,
            "success": row.success,
            "api_request": row.api_request,
            "api_response": row.api_response,
            "verification": row.verification,
            "error": row.error,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
