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
    version = "9.0.1"

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
                    "quota_aware_marketplace_requests",
                    "open_job_status_summary",
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
        respect_quota: bool = True,
        quota_backoff_minutes: int = 60,
        max_marketplaces_per_run: int | None = None,
    ) -> dict[str, Any]:
        target_date = date or SellerCentralAutomationService.yesterday_date()
        marketplace_list = SellerCentralAutomationService._marketplace_list(marketplaces)
        if max_marketplaces_per_run is None:
            max_marketplaces_per_run = SellerCentralAutomationService._max_marketplaces_per_run()

        quota_state = SPAPIReportPipelineService.recent_quota_limited_marketplaces(minutes=quota_backoff_minutes)
        quota_blocked = set(quota_state.get("marketplaces", [])) if respect_quota else set()
        results = []
        requested_count = 0

        for marketplace in marketplace_list:
            if marketplace in quota_blocked:
                results.append({
                    "marketplace": marketplace,
                    "status": "SKIPPED_QUOTA_BACKOFF",
                    "message": f"Skipped {marketplace}; a recent SP-API quota error exists within {quota_backoff_minutes} minutes.",
                    "next_step": "Collect existing jobs and retry this marketplace after the backoff window.",
                })
                continue
            if max_marketplaces_per_run and requested_count >= max_marketplaces_per_run:
                results.append({
                    "marketplace": marketplace,
                    "status": "SKIPPED_BATCH_LIMIT",
                    "message": f"Skipped {marketplace}; max_marketplaces_per_run={max_marketplaces_per_run} prevents back-to-back quota pressure.",
                    "next_step": "Run the request again later for the remaining marketplace(s).",
                })
                continue

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
            requested_count += 1
            results.append({"marketplace": marketplace, "status": result.get("status"), "result": result})

        request_errors = [r for r in results if r.get("status") in {"ERROR", "QUOTA_LIMITED"} or (r.get("result") or {}).get("status") in {"ERROR", "QUOTA_LIMITED"}]
        return {
            "status": "OK" if not request_errors else "PARTIAL",
            "version": SellerCentralAutomationService.version,
            "date": target_date,
            "requested_marketplaces": marketplace_list,
            "requested_count": requested_count,
            "quota_backoff": {
                "enabled": respect_quota,
                "minutes": quota_backoff_minutes,
                "blocked_marketplaces": sorted(quota_blocked),
            },
            "results": results,
            "next_step": "Run POST /business-os/sp-api/automation/open-jobs/collect until jobs are collected. Requests are quota-aware, so skipped marketplaces can be retried later.",
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
        done = 0
        for job_id in job_ids:
            result = SPAPIReportPipelineService.collect_job(job_id)
            status = result.get("status")
            if status == "COLLECTED":
                collected += 1
            elif status == "PENDING":
                pending += 1
            elif status == "DONE":
                done += 1
            elif status in {"ERROR", "NOT_FOUND"}:
                errors += 1
            results.append({"job_id": job_id, "status": status, "result": result})

        summary = SPAPIReportPipelineService.summarize_jobs()
        return {
            "status": "OK" if errors == 0 else "PARTIAL",
            "version": SellerCentralAutomationService.version,
            "checked_jobs": len(job_ids),
            "collected": collected,
            "pending": pending,
            "done": done,
            "errors": errors,
            "results": results,
            "job_summary": summary,
            "next_step": SellerCentralAutomationService._collect_next_step(collected, pending, errors, summary),
        }

    @staticmethod
    def collect_until_idle(limit: int = 25, max_rounds: int = 3) -> dict[str, Any]:
        """Collect open jobs for a few rounds without sleeping.

        This is safe for Swagger/manual use. It will not wait minutes inside a web
        request; it simply collects anything already DONE and reports remaining
        pending jobs clearly.
        """
        rounds = []
        for _ in range(max(1, min(max_rounds, 5))):
            result = SellerCentralAutomationService.collect_open_jobs(limit=limit)
            rounds.append(result)
            if result.get("pending", 0) == 0 and result.get("done", 0) == 0:
                break
        final = rounds[-1] if rounds else {}
        return {
            "status": final.get("status", "OK"),
            "version": SellerCentralAutomationService.version,
            "rounds": len(rounds),
            "results": rounds,
            "final_summary": final.get("job_summary"),
            "next_step": final.get("next_step"),
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
    def _max_marketplaces_per_run() -> int:
        raw = os.getenv("SP_API_MAX_MARKETPLACES_PER_RUN") or os.getenv("SELLER_CENTRAL_MAX_MARKETPLACES_PER_RUN")
        try:
            return max(1, min(int(raw), 10)) if raw else 1
        except Exception:
            return 1

    @staticmethod
    def _collect_next_step(collected: int, pending: int, errors: int, summary: dict[str, Any]) -> str:
        if errors:
            return "Some jobs errored. Inspect result.error_message and retry only after fixing the cause."
        if collected:
            return "Seller Central data was ingested. Recheck Revenue Intelligence / organic-vs-paid."
        if pending:
            return "Reports are still queued/processing at Amazon. Run this endpoint again in a few minutes."
        counts = (summary or {}).get("counts", {})
        if counts.get("QUOTA_LIMITED", 0):
            return "No collectable jobs. Some marketplaces are quota-limited; wait before requesting more reports."
        return "No open jobs found. Request a new Sales & Traffic report when ready."

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
