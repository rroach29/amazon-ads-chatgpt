"""Business OS v8.3 — Planning Foundation.

This module exposes typed planning contracts without changing Mission Control's
current behavior. v8.4 can build the Executive Planning Engine on these models.
"""

from __future__ import annotations

from typing import Any

from domain import ActionGroup, Initiative, Objective, Plan, Decision
from optimizers.optimizer_registry import optimizer_manifests


class PlanningFoundation:
    @staticmethod
    def describe() -> dict[str, Any]:
        return {
            "status": "OK",
            "schema_version": "8.3",
            "planning_models": ["Plan", "Initiative", "ActionGroup", "ExecutionPhase", "StrategicObjective"],
            "inputs": ["optimizer_opportunities", "decisions", "business_objective", "knowledge_graph", "learning_outcomes"],
            "future_release": "v8.4 Executive Planning Engine",
            "optimizer_manifests": optimizer_manifests(),
            "narrative": "Planning foundation is installed. Mission Control behavior remains unchanged until the Executive Planning Engine is enabled.",
        }

    @staticmethod
    def sample() -> dict[str, Any]:
        decision = Decision(
            decision="INCREASE_BID",
            priority="MEDIUM",
            confidence=85,
            risk="MEDIUM",
            estimated_monthly_impact=281.94,
            recommended_action="Increase bid by 20% for proven search term",
            optimizer_name="bid_optimizer",
            optimizer_version="6.1.0",
            optimizer_class="BidOptimizer",
        )
        group = ActionGroup(
            title="Scale proven advertising winners",
            actions=[decision],
            estimated_monthly_impact=281.94,
            confidence=85,
            risk="MEDIUM",
        )
        initiative = Initiative(
            title="Grow efficient PET PHOTO demand",
            objective="MAXIMIZE_PROFIT",
            action_groups=[group],
            estimated_monthly_impact=281.94,
            confidence=85,
            risk="MEDIUM",
            priority_score=91,
            narrative="Scale the best proven traffic while keeping risk controlled.",
        )
        plan = Plan(
            title="Sample Executive Plan",
            objective=Objective(objective_id="MAXIMIZE_PROFIT", label="Maximize Profit"),
            initiatives=[initiative],
            estimated_monthly_impact=281.94,
            confidence=85,
            risk="MEDIUM",
        )
        return {"status": "OK", "schema_version": "8.3", "plan": plan.to_dict()}
