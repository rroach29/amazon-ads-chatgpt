"""Business OS v0.5.0 — Executive Inbox.

A daily work inbox built on top of Mission Control v2 and Execution Framework.
"""

from __future__ import annotations

from typing import Any

from business_os.execution_framework.planner import ExecutionPlannerService
from business_os.mission_control_v2.service import MissionControlV2Service


class ExecutiveInboxService:
    version = "business-os-0.5.0"

    @classmethod
    def inbox(cls, limit: int = 50) -> dict[str, Any]:
        queue = MissionControlV2Service.executive_queue(limit=limit, include_setup=False)
        plans = ExecutionPlannerService.list_plans(limit=25)

        top_three = queue.get("top_three", [])
        ready_plans = [p for p in plans.get("plans", []) if p.get("status") in ["Planned", "Ready", "Approved"]]
        dry_run_complete = [p for p in plans.get("plans", []) if p.get("status") == "DryRunComplete"]

        return {
            "status": "OK",
            "version": cls.version,
            "greeting": "Good morning Rob",
            "summary": {
                "urgent_decisions": len(top_three),
                "business_decisions": queue.get("summary", {}).get("business_decisions", 0),
                "setup_backlog": queue.get("summary", {}).get("setup_backlog", 0),
                "top_three_estimated_monthly_impact": queue.get("summary", {}).get("top_three_estimated_monthly_impact", 0),
                "execution_plans_ready": len(ready_plans),
                "dry_runs_completed": len(dry_run_complete),
            },
            "top_three": top_three,
            "next_ten": queue.get("next_ten", []),
            "execution_plans": ready_plans[:10],
            "recent_execution_results": dry_run_complete[:10],
        }
