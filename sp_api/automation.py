"""Business OS v9.0 — Seller Central automation service.

This layer turns the working v8.9 Seller Central report pipeline into a
repeatable operating workflow:
- request yesterday's Sales & Traffic reports for configured marketplaces
- collect open jobs that are ready
- expose a single nightly run action for Swagger/manual validation

It intentionally reuses SPAPIReportPipelineService instead of duplicating
request, poll, download, and ingestion logic.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from database import SessionLocal
from models import SPAPIReportJob, SellerCentralSalesTraffic
from sp_api.pipeline import SPAPIReportPipelineService


class SellerCentralAutomationService:
    version = "9.0"

    @staticmethod
    def diagnostics() -> dict[str, Any]:
        db = SessionLocal()
        try:
            open_jobs = (
                db.query(SPAPIReportJob)
                .filter(SPAPIReportJob.status.in_(["REQUESTED", "PROCESSING", "DONE"]))
                .count()
            )
            collected_jobs = db.query(SPAPIReportJob).filter(SPAPIReportJob.status == "COLLECTED").count()
            seller_rows = db.query(SellerCentralSalesTraffic).count()
            latest_job = db.query(SPAPIReportJob).order_by(SPAPIReportJob.created_at.desc()).first()
            return {
                "status": "OK",
                "version": SellerCentralAutomationService.version,
                "automation": "seller_central_sales_traffic",
                "default_marketplaces": SellerCentralAutomationService.default_marketplaces(),
                "counts": {
                    "open_jobs": open_jobs,
                    "collected_jobs": collected_jobs,
                    "seller_central_sales_traffic_rows": seller_rows,
                },
                "latest_job": SPAPIReportPipelineService._job_to_dict(latest_job) if latest_job else None,
                "capabilities": [
                    "request_yesterday_sales_traffic",
                    "collect_open_sales_traffic_jobs",
                    "nightly_run",
                    "revenue_reconciliation_ready",
                ],
                "note": "Use POST /business-os/sp-api/automation/nightly/run to request yesterday reports and collect any completed open jobs.",
            }
        except Exception as exc:
            return {"status": "ERROR", "version": SellerCentralAutomationService.version, "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def default_marketplaces() -> list[str]:
        configured = os.getenv("SP_API_DEFAULT_MARKETPLACES") or os.getenv("SELLER_CENTRAL_DEFAULT_MARKETPLACES")
        if configured:
            return [m.strip().upper() for m in configured.split(",") if m.strip()]
        return ["US", "CA"]

    @staticmethod
    def yesterday_date() -> str:
        return (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()

    @staticmethod
    def request_yesterday(
        marketplaces: str | None = None,
        date: str | None = None,
        asin_granularity: str = "CHILD",
        date_granularity: str = "DAY",
    ) -> dict[str, Any]:
        target_date = date or SellerCentralAutomationService.yesterday_date()
        marketplace_list = SellerCentralAutomationService._marketplace_list(marketplaces)
        results = []
        for marketplace in marketplace_list:
            currency = SellerCentralAutomationService._currency_for_marketplace(marketplace)
            result = SPAPIReportPipelineService.request_sales_traffic_job(
                start_date=target_date,
                end_date=target_date,
                marketplace=marketplace,
                country_code=marketplace,
                currency=currency,
                asin_granularity=asin_granularity,
                date_granularity=date_granularity,
            )
            results.append({"marketplace": marketplace, "result": result})
        return {
            "status": "OK" if all((r.get("result") or {}).get("status") not in {"ERROR"} for r in results) else "PARTIAL",
            "version": SellerCentralAutomationService.version,
            "date": target_date,
            "requested_marketplaces": marketplace_list,
            "results": results,
            "next_step": "Run POST /business-os/sp-api/automation/open-jobs/collect until jobs are collected.",
        }

    @staticmethod
    def collect_open_jobs(limit: int = 25) -> dict[str, Any]:
        db = SessionLocal()
        try:
            jobs = (
                db.query(SPAPIReportJob)
                .filter(SPAPIReportJob.report_type == "GET_SALES_AND_TRAFFIC_REPORT")
                .filter(SPAPIReportJob.status.in_(["REQUESTED", "PROCESSING", "DONE"]))
                .order_by(SPAPIReportJob.created_at.asc())
                .limit(max(1, min(limit, 100)))
                .all()
            )
            job_ids = [job.id for job in jobs]
        finally:
            db.close()

        results = []
        collected = 0
        pending = 0
        errors = 0
        for job_id in job_ids:
            result = SPAPIReportPipelineService.collect_job(job_id)
            status = result.get("status")
            if status == "COLLECTED":
                collected += 1
            elif status == "PENDING":
                pending += 1
            elif status in {"ERROR", "NOT_FOUND"}:
                errors += 1
            results.append({"job_id": job_id, "status": status, "result": result})

        return {
            "status": "OK" if errors == 0 else "PARTIAL",
            "version": SellerCentralAutomationService.version,
            "checked_jobs": len(job_ids),
            "collected": collected,
            "pending": pending,
            "errors": errors,
            "results": results,
        }

    @staticmethod
    def nightly_run(
        marketplaces: str | None = None,
        date: str | None = None,
        collect_existing_first: bool = True,
    ) -> dict[str, Any]:
        before_collect = SellerCentralAutomationService.collect_open_jobs() if collect_existing_first else None
        requested = SellerCentralAutomationService.request_yesterday(marketplaces=marketplaces, date=date)
        after_collect = SellerCentralAutomationService.collect_open_jobs()
        return {
            "status": "OK" if requested.get("status") in {"OK", "PARTIAL"} else requested.get("status"),
            "version": SellerCentralAutomationService.version,
            "mode": "manual_or_scheduler_safe_nightly_run",
            "date": date or SellerCentralAutomationService.yesterday_date(),
            "before_collect": before_collect,
            "requested": requested,
            "after_collect": after_collect,
            "next_step": "Run again later if any reports are still pending. Amazon report generation is asynchronous.",
        }

    @staticmethod
    def _marketplace_list(marketplaces: str | None) -> list[str]:
        if marketplaces:
            items = [m.strip().upper() for m in marketplaces.split(",") if m.strip()]
            return items or SellerCentralAutomationService.default_marketplaces()
        return SellerCentralAutomationService.default_marketplaces()

    @staticmethod
    def _currency_for_marketplace(marketplace: str | None) -> str | None:
        mapping = {"US": "USD", "CA": "CAD", "MX": "MXN"}
        return mapping.get(str(marketplace or "").upper())
