"""Business OS ChangeSets 1.0.

Turns decisions into reviewable proposed changes before approval.
This first slice is intentionally non-destructive and derives a change set from
existing Mission Control decisions plus the Execution Framework inference.
"""

from __future__ import annotations

from typing import Any

from database import SessionLocal
from business_os.mission_control.models import MissionControlDecision
from business_os.execution_framework.planner import ExecutionPlannerService


class ChangeSetService:
    version = "business-os-0.7.0-change-sets"

    @classmethod
    def for_decision(cls, decision_id: str) -> dict[str, Any]:
        db = SessionLocal()
        try:
            decision = db.query(MissionControlDecision).filter(MissionControlDecision.decision_id == decision_id).first()
            if not decision:
                return {"status": "NOT_FOUND", "version": cls.version, "message": f"Decision {decision_id} not found."}

            executable = ExecutionPlannerService._infer_execution(decision)
            simulation = ExecutionPlannerService._simulation(decision, executable)
            changes = cls._changes(decision, executable)

            return {
                "status": "OK",
                "version": cls.version,
                "decision_id": decision_id,
                "title": decision.title or executable.get("title") or "Proposed business change",
                "product": {
                    "master_product_id": decision.master_product_id,
                    "product_name": decision.product_name,
                },
                "marketplace": cls._marketplace(decision, executable),
                "summary": {
                    "change_count": len(changes),
                    "expected_monthly_impact": float(decision.estimated_monthly_impact or 0),
                    "confidence": int(decision.confidence or 0),
                    "risk_level": executable.get("risk_level"),
                    "can_execute_live": simulation.get("can_execute_live"),
                    "missing_fields": simulation.get("missing_fields") or [],
                },
                "target": cls._target(decision, executable),
                "changes": changes,
                "evidence": cls._evidence(decision),
                "rollback": cls._rollback(executable, changes),
                "simulation": simulation,
                "raw_executable": executable,
            }
        finally:
            db.close()

    @classmethod
    def _changes(cls, decision: MissionControlDecision, executable: dict[str, Any]) -> list[dict[str, Any]]:
        action = executable.get("action_type") or "manual_review"
        evidence = cls._evidence_map(decision)
        keyword = executable.get("keyword_text") or evidence.get("search_term") or evidence.get("keyword")
        campaign = evidence.get("campaign_name") or evidence.get("campaign") or executable.get("campaign_name")
        ad_group = evidence.get("ad_group_name") or evidence.get("ad_group") or executable.get("ad_group_name")
        campaign_id = evidence.get("campaign_id") or executable.get("campaign_id")
        ad_group_id = evidence.get("ad_group_id") or executable.get("ad_group_id")

        base_target = {
            "platform": executable.get("platform"),
            "marketplace": evidence.get("marketplace") or evidence.get("country_code"),
            "campaign_name": campaign,
            "campaign_id": campaign_id,
            "ad_group_name": ad_group,
            "ad_group_id": ad_group_id,
            "product_name": decision.product_name,
            "master_product_id": decision.master_product_id,
        }

        if action == "add_exact_keyword":
            return [
                {
                    "change_id": f"{decision.decision_id}-ADD-EXACT",
                    "change_type": "keyword_add",
                    "title": f"Add Exact keyword: {keyword or 'search term'}",
                    "target": base_target,
                    "current": {"exists": False, "keyword_text": None, "match_type": None, "bid": None},
                    "proposed": {
                        "exists": True,
                        "keyword_text": keyword,
                        "match_type": "exact",
                        "bid": executable.get("suggested_bid"),
                    },
                    "diff": [f"+ exact keyword: {keyword or 'search term'}"],
                    "requires": executable.get("requires") or [],
                    "missing_fields": executable.get("missing_fields") or [],
                    "expected_impact": cls._impact(decision),
                }
            ]

        if action == "add_negative_keyword":
            return [
                {
                    "change_id": f"{decision.decision_id}-ADD-NEGATIVE",
                    "change_type": "negative_keyword_add",
                    "title": f"Add Negative Exact keyword: {keyword or 'search term'}",
                    "target": base_target,
                    "current": {"negative_exists": False, "keyword_text": None, "match_type": None},
                    "proposed": {
                        "negative_exists": True,
                        "keyword_text": keyword,
                        "match_type": executable.get("match_type") or "negativeExact",
                    },
                    "diff": [f"+ negative exact: {keyword or 'search term'}"],
                    "requires": executable.get("requires") or [],
                    "missing_fields": executable.get("missing_fields") or [],
                    "expected_impact": cls._impact(decision),
                }
            ]

        if action in {"decrease_bid", "increase_bid"}:
            return [
                {
                    "change_id": f"{decision.decision_id}-BID",
                    "change_type": "bid_update",
                    "title": executable.get("title") or "Update bid",
                    "target": base_target | {"entity": executable.get("entity")},
                    "current": {"bid": evidence.get("current_bid") or executable.get("current_bid")},
                    "proposed": {"bid": evidence.get("new_bid") or executable.get("new_bid")},
                    "diff": ["~ update bid"],
                    "requires": executable.get("requires") or [],
                    "missing_fields": executable.get("missing_fields") or [],
                    "expected_impact": cls._impact(decision),
                }
            ]

        return [
            {
                "change_id": f"{decision.decision_id}-MANUAL",
                "change_type": "manual_review",
                "title": executable.get("title") or decision.title or "Manual review",
                "target": base_target,
                "current": {"state": "No automated change prepared"},
                "proposed": {"state": decision.recommendation or decision.title},
                "diff": ["~ manual review required"],
                "requires": executable.get("requires") or [],
                "missing_fields": executable.get("missing_fields") or [],
                "expected_impact": cls._impact(decision),
            }
        ]

    @staticmethod
    def _target(decision: MissionControlDecision, executable: dict[str, Any]) -> dict[str, Any]:
        evidence = ChangeSetService._evidence_map(decision)
        return {
            "platform": executable.get("platform"),
            "marketplace": evidence.get("marketplace") or evidence.get("country_code"),
            "campaign_name": evidence.get("campaign_name") or evidence.get("campaign"),
            "campaign_id": evidence.get("campaign_id"),
            "ad_group_name": evidence.get("ad_group_name") or evidence.get("ad_group"),
            "ad_group_id": evidence.get("ad_group_id"),
            "asin": evidence.get("asin"),
            "sku": evidence.get("sku"),
        }

    @staticmethod
    def _marketplace(decision: MissionControlDecision, executable: dict[str, Any]) -> dict[str, Any]:
        evidence = ChangeSetService._evidence_map(decision)
        return {
            "platform": executable.get("platform"),
            "country_code": evidence.get("country_code") or evidence.get("marketplace"),
        }

    @staticmethod
    def _evidence(decision: MissionControlDecision) -> list[dict[str, Any]]:
        evidence = decision.evidence if isinstance(decision.evidence, list) else []
        if evidence:
            return evidence
        output = []
        for label, value in [
            ("reason", decision.reason),
            ("why_now", decision.why_now),
            ("recommendation", decision.recommendation),
            ("source", decision.source),
        ]:
            if value:
                output.append({"signal": label, "value": value})
        return output

    @staticmethod
    def _evidence_map(decision: MissionControlDecision) -> dict[str, Any]:
        evidence = decision.evidence if isinstance(decision.evidence, list) else []
        output: dict[str, Any] = {}
        for item in evidence:
            if not isinstance(item, dict):
                continue
            signal = item.get("signal") or item.get("name") or item.get("key")
            value = item.get("value") if "value" in item else item.get("data")
            if signal:
                output[str(signal)] = value
            for key, val in item.items():
                if key not in {"signal", "name", "key", "value", "data"} and val is not None:
                    output.setdefault(key, val)
        return output

    @staticmethod
    def _impact(decision: MissionControlDecision) -> dict[str, Any]:
        return {
            "estimated_monthly_impact": float(decision.estimated_monthly_impact or 0),
            "confidence": int(decision.confidence or 0),
            "reason": decision.reason,
        }

    @staticmethod
    def _rollback(executable: dict[str, Any], changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rollbacks = []
        for change in changes:
            change_type = change.get("change_type")
            if change_type == "keyword_add":
                rollbacks.append({"rollback_type": "keyword_remove", "target": change.get("target"), "value": change.get("proposed")})
            elif change_type == "negative_keyword_add":
                rollbacks.append({"rollback_type": "negative_keyword_remove", "target": change.get("target"), "value": change.get("proposed")})
            elif change_type == "bid_update":
                rollbacks.append({"rollback_type": "restore_bid", "target": change.get("target"), "value": change.get("current")})
            else:
                rollbacks.append({"rollback_type": "manual", "target": change.get("target"), "value": "Review manually"})
        return rollbacks
