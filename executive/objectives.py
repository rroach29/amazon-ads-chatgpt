"""
Business OS v8.0 — Business Objectives

Configurable objective metadata used by Mission Control 2.0. This is deliberately
stateless for v8.0 so it can be deployed without a SQL migration. A future release
can persist selected objectives per marketplace/business unit.
"""

from __future__ import annotations

from typing import Any


class BusinessObjectives:
    DEFAULT_OBJECTIVE = "maximize_profit"

    OBJECTIVES: dict[str, dict[str, Any]] = {
        "maximize_profit": {
            "key": "maximize_profit",
            "label": "Maximize Profit",
            "description": "Prioritize efficient growth, wasted-spend reduction, and profitable scaling.",
            "risk_tolerance": "MEDIUM",
            "weights": {
                "impact": 0.40,
                "confidence": 0.25,
                "risk": 0.20,
                "efficiency": 0.15,
            },
            "preferred_decisions": [
                "ADD_NEGATIVE_KEYWORD",
                "REDUCE_BID",
                "INCREASE_BID",
                "INCREASE_BUDGET",
                "DECREASE_BUDGET",
            ],
        },
        "maximize_sales": {
            "key": "maximize_sales",
            "label": "Maximize Sales",
            "description": "Prioritize scalable campaigns and controlled bid/budget increases.",
            "risk_tolerance": "MEDIUM_HIGH",
            "weights": {
                "impact": 0.45,
                "confidence": 0.20,
                "risk": 0.10,
                "growth": 0.25,
            },
            "preferred_decisions": [
                "INCREASE_BUDGET",
                "INCREASE_BID",
                "HARVEST_KEYWORD",
            ],
        },
        "preserve_cash": {
            "key": "preserve_cash",
            "label": "Preserve Cash",
            "description": "Prioritize spend reduction, reversibility, and low-risk efficiency actions.",
            "risk_tolerance": "LOW",
            "weights": {
                "impact": 0.30,
                "confidence": 0.30,
                "risk": 0.30,
                "cash_protection": 0.10,
            },
            "preferred_decisions": [
                "ADD_NEGATIVE_KEYWORD",
                "REDUCE_BID",
                "DECREASE_BUDGET",
                "PAUSE_CAMPAIGN",
            ],
        },
        "launch_product": {
            "key": "launch_product",
            "label": "Launch Product",
            "description": "Prioritize visibility and learning while keeping guardrails on risk.",
            "risk_tolerance": "MEDIUM_HIGH",
            "weights": {
                "impact": 0.30,
                "confidence": 0.15,
                "risk": 0.10,
                "learning": 0.20,
                "growth": 0.25,
            },
            "preferred_decisions": [
                "INCREASE_BID",
                "INCREASE_BUDGET",
                "HARVEST_KEYWORD",
            ],
        },
        "defend_market_share": {
            "key": "defend_market_share",
            "label": "Defend Market Share",
            "description": "Prioritize preserving strong campaigns, visibility, and converting traffic.",
            "risk_tolerance": "MEDIUM",
            "weights": {
                "impact": 0.35,
                "confidence": 0.20,
                "risk": 0.15,
                "growth": 0.20,
                "stability": 0.10,
            },
            "preferred_decisions": [
                "INCREASE_BID",
                "INCREASE_BUDGET",
                "HARVEST_KEYWORD",
                "ADD_NEGATIVE_KEYWORD",
            ],
        },
        "liquidate_inventory": {
            "key": "liquidate_inventory",
            "label": "Liquidate Inventory",
            "description": "Prioritize sales velocity and budget allocation to products that need movement.",
            "risk_tolerance": "HIGH",
            "weights": {
                "impact": 0.45,
                "confidence": 0.15,
                "risk": 0.05,
                "growth": 0.35,
            },
            "preferred_decisions": [
                "INCREASE_BUDGET",
                "INCREASE_BID",
                "HARVEST_KEYWORD",
            ],
        },
    }

    @classmethod
    def normalize(cls, objective: str | None = None) -> str:
        key = (objective or cls.DEFAULT_OBJECTIVE).strip().lower().replace(" ", "_")
        return key if key in cls.OBJECTIVES else cls.DEFAULT_OBJECTIVE

    @classmethod
    def get(cls, objective: str | None = None) -> dict[str, Any]:
        return dict(cls.OBJECTIVES[cls.normalize(objective)])

    @classmethod
    def list(cls) -> dict[str, Any]:
        return {
            "status": "OK",
            "default_objective": cls.DEFAULT_OBJECTIVE,
            "count": len(cls.OBJECTIVES),
            "objectives": list(cls.OBJECTIVES.values()),
        }
