"""Business OS v8.9 — Seller Central Sales & Traffic data pipeline.

This module turns the v8.8/v8.8.1 live SP-API connector into a persistent
report pipeline:

1. Request GET_SALES_AND_TRAFFIC_REPORT.
2. Store the report job and Amazon reportId.
3. Poll processing status.
4. Download the report document once DONE.
5. Ingest rows into seller_central_sales_traffic.
6. Preserve lifecycle state for Swagger, diagnostics, and future scheduler use.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from database import SessionLocal
from models import SPAPIReportJob, SellerCentralSalesTraffic
from sp_api.client import SPAPIClient, SPAPIConfig
from sp_api.sales_traffic import SalesTrafficIngestionService


class SPAPIReportPipelineService:
    version = "9.0.1"

    @staticmethod
    def diagnostics() -> dict[str, Any]:
        db = SessionLocal()
        try:
            job_count = db.query(SPAPIReportJob).count()
            seller_rows = db.query(SellerCentralSalesTraffic).count()
            latest = (
                db.query(SPAPIReportJob)
                .order_by(SPAPIReportJob.created_at.desc())
                .first()
            )
            return {
                "status": "OK",
                "version": SPAPIReportPipelineService.version,
                "pipeline": "seller_central_sales_traffic",
                "counts": {
                    "sp_api_report_jobs": job_count,
                    "seller_central_sales_traffic_rows": seller_rows,
                },
                "latest_job": SPAPIReportPipelineService._job_to_dict(latest) if latest else None,
                "capabilities": [
                    "request_sales_traffic_report",
                    "poll_report_status",
                    "download_report_document",
                    "ingest_sales_traffic_rows",
                    "persistent_job_history",
                    "quota_aware_request_status",
                    "confidence_reasoning_support",
                ],
            }
        except Exception as exc:
            return {"status": "ERROR", "version": SPAPIReportPipelineService.version, "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def request_sales_traffic_job(
        start_date: str,
        end_date: str,
        marketplace: str | None = None,
        marketplace_id: str | None = None,
        country_code: str | None = None,
        currency: str | None = None,
        profile_id: str | None = None,
        asin_granularity: str = "CHILD",
        date_granularity: str = "DAY",
    ) -> dict[str, Any]:
        normalized_marketplace = SPAPIReportPipelineService._normalize_marketplace(marketplace or country_code or marketplace_id)
        client = SPAPIClient(SPAPIConfig.from_env(normalized_marketplace))
        resolved_marketplace_id = client._resolve_marketplace_id(marketplace_id or client.config.marketplace_id or normalized_marketplace)
        requested = client.request_sales_and_traffic_report(
            start_date=start_date,
            end_date=end_date,
            marketplace_id=resolved_marketplace_id,
            asin_granularity=asin_granularity,
            date_granularity=date_granularity,
        )
        db = SessionLocal()
        try:
            job = SPAPIReportJob(
                report_type="GET_SALES_AND_TRAFFIC_REPORT",
                requested_at=SPAPIReportPipelineService._now(),
                status=SPAPIReportPipelineService._initial_status_for_request(requested),
                marketplace=normalized_marketplace,
                marketplace_id=resolved_marketplace_id,
                country_code=(country_code or normalized_marketplace or "").upper() or None,
                currency=currency,
                profile_id=profile_id,
                start_date=SPAPIReportPipelineService._parse_date(start_date),
                end_date=SPAPIReportPipelineService._parse_date(end_date),
                asin_granularity=asin_granularity,
                date_granularity=date_granularity,
                request_payload={
                    "start_date": start_date,
                    "end_date": end_date,
                    "marketplace": normalized_marketplace,
                    "marketplace_id": resolved_marketplace_id,
                    "dataStartTime": client._report_timestamp(start_date, end_of_day=False),
                    "dataEndTime": client._report_timestamp(end_date, end_of_day=True),
                    "asin_granularity": asin_granularity,
                    "date_granularity": date_granularity,
                },
                response_payload=requested,
                error_message=None if requested.get("status") == "OK" else requested.get("message") or str(requested),
            )
            if requested.get("status") == "OK":
                response = requested.get("response", {}) or {}
                job.report_id = response.get("reportId")
                job.processing_status = response.get("processingStatus") or "SUBMITTED"
            db.add(job)
            db.commit()
            db.refresh(job)
            return {
                "status": job.status,
                "version": SPAPIReportPipelineService.version,
                "job": SPAPIReportPipelineService._job_to_dict(job),
                "next_step": SPAPIReportPipelineService._next_step_for_job(job),
            }
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": SPAPIReportPipelineService.version, "message": str(exc), "request": requested}
        finally:
            db.close()

    @staticmethod
    def list_jobs(limit: int = 25) -> dict[str, Any]:
        db = SessionLocal()
        try:
            rows = (
                db.query(SPAPIReportJob)
                .order_by(SPAPIReportJob.created_at.desc())
                .limit(max(1, min(limit, 250)))
                .all()
            )
            return {
                "status": "OK",
                "version": SPAPIReportPipelineService.version,
                "count": len(rows),
                "jobs": [SPAPIReportPipelineService._job_to_dict(row) for row in rows],
            }
        finally:
            db.close()

    @staticmethod
    def get_job(job_id: int) -> dict[str, Any]:
        db = SessionLocal()
        try:
            job = db.query(SPAPIReportJob).filter(SPAPIReportJob.id == job_id).first()
            if not job:
                return {"status": "NOT_FOUND", "job_id": job_id}
            return {"status": "OK", "version": SPAPIReportPipelineService.version, "job": SPAPIReportPipelineService._job_to_dict(job)}
        finally:
            db.close()

    @staticmethod
    def poll_job(job_id: int) -> dict[str, Any]:
        db = SessionLocal()
        try:
            job = db.query(SPAPIReportJob).filter(SPAPIReportJob.id == job_id).first()
            if not job:
                return {"status": "NOT_FOUND", "job_id": job_id}
            if not job.report_id:
                return {"status": "ERROR", "message": "Job has no report_id.", "job": SPAPIReportPipelineService._job_to_dict(job)}
            client = SPAPIClient(SPAPIConfig.from_env(job.marketplace))
            report = client.get_report(job.report_id)
            job.updated_at = SPAPIReportPipelineService._now()
            job.response_payload = report
            if report.get("status") == "OK":
                response = report.get("response", {}) or {}
                job.processing_status = response.get("processingStatus")
                job.report_document_id = response.get("reportDocumentId") or job.report_document_id
                if job.processing_status == "DONE":
                    job.status = "DONE"
                elif job.processing_status in {"CANCELLED", "FATAL"}:
                    job.status = "ERROR"
                    job.error_message = f"Amazon report processing status: {job.processing_status}"
                else:
                    job.status = "PROCESSING"
            else:
                job.status = "ERROR"
                job.error_message = report.get("message") or str(report)
            db.commit()
            db.refresh(job)
            return {"status": job.status, "version": SPAPIReportPipelineService.version, "job": SPAPIReportPipelineService._job_to_dict(job)}
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": SPAPIReportPipelineService.version, "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def collect_job(job_id: int) -> dict[str, Any]:
        db = SessionLocal()
        try:
            job = db.query(SPAPIReportJob).filter(SPAPIReportJob.id == job_id).first()
            if not job:
                return {"status": "NOT_FOUND", "job_id": job_id}
            if not job.report_id:
                return {"status": "ERROR", "message": "Job has no report_id.", "job": SPAPIReportPipelineService._job_to_dict(job)}

            if job.processing_status != "DONE" or not job.report_document_id:
                # Poll once so Swagger users do not have to remember two steps.
                poll_result = SPAPIReportPipelineService.poll_job(job_id)
                if poll_result.get("status") != "DONE":
                    return {"status": "PENDING", "poll": poll_result}
                db.refresh(job)

            client = SPAPIClient(SPAPIConfig.from_env(job.marketplace))
            document = client.get_report_document(job.report_document_id)
            if document.get("status") != "OK":
                job.status = "ERROR"
                job.error_message = document.get("message") or str(document)
                job.updated_at = SPAPIReportPipelineService._now()
                job.response_payload = document
                db.commit()
                return {"status": "ERROR", "message": "Could not fetch report document metadata.", "document": document}

            downloaded = client.download_report_document(document.get("response", {}) or {})
            if downloaded.get("status") != "OK":
                job.status = "ERROR"
                job.error_message = downloaded.get("message") or str(downloaded)
                job.updated_at = SPAPIReportPipelineService._now()
                job.response_payload = downloaded
                db.commit()
                return {"status": "ERROR", "message": "Could not download report document.", "download": downloaded}

            ingest = SalesTrafficIngestionService.ingest_payload(
                downloaded.get("document"),
                country_code=job.country_code,
                marketplace=job.marketplace,
                marketplace_id=job.marketplace_id,
                currency=job.currency,
                profile_id=job.profile_id,
            )
            job.status = "COLLECTED" if ingest.get("status") == "OK" else "ERROR"
            job.completed_at = SPAPIReportPipelineService._now() if ingest.get("status") == "OK" else None
            job.updated_at = SPAPIReportPipelineService._now()
            job.collect_result = ingest
            job.response_payload = {"document": document, "download": {k: v for k, v in downloaded.items() if k != "document"}}
            if ingest.get("status") != "OK":
                job.error_message = ingest.get("message") or str(ingest)
            db.commit()
            db.refresh(job)
            return {
                "status": job.status,
                "version": SPAPIReportPipelineService.version,
                "job": SPAPIReportPipelineService._job_to_dict(job),
                "ingestion": ingest,
            }
        except Exception as exc:
            db.rollback()
            return {"status": "ERROR", "version": SPAPIReportPipelineService.version, "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def run_once(
        start_date: str,
        end_date: str,
        marketplace: str | None = None,
        marketplace_id: str | None = None,
        country_code: str | None = None,
        currency: str | None = None,
        profile_id: str | None = None,
        asin_granularity: str = "CHILD",
        date_granularity: str = "DAY",
    ) -> dict[str, Any]:
        requested = SPAPIReportPipelineService.request_sales_traffic_job(
            start_date=start_date,
            end_date=end_date,
            marketplace=marketplace,
            marketplace_id=marketplace_id,
            country_code=country_code,
            currency=currency,
            profile_id=profile_id,
            asin_granularity=asin_granularity,
            date_granularity=date_granularity,
        )
        job = requested.get("job") or {}
        job_id = job.get("id")
        if not job_id or requested.get("status") == "ERROR":
            return requested
        polled = SPAPIReportPipelineService.poll_job(int(job_id))
        if polled.get("status") == "DONE":
            collected = SPAPIReportPipelineService.collect_job(int(job_id))
            return {"status": collected.get("status"), "version": SPAPIReportPipelineService.version, "requested": requested, "polled": polled, "collected": collected}
        return {
            "status": "REQUESTED",
            "version": SPAPIReportPipelineService.version,
            "requested": requested,
            "polled": polled,
            "next_step": f"Report is asynchronous. Run POST /business-os/sp-api/pipeline/jobs/{job_id}/collect after Amazon marks it DONE.",
        }

    @staticmethod
    def summarize_jobs() -> dict[str, Any]:
        """Return a compact operational view of SP-API report jobs."""
        db = SessionLocal()
        try:
            statuses = ["REQUESTED", "PROCESSING", "DONE", "COLLECTED", "ERROR", "QUOTA_LIMITED"]
            counts = {status: db.query(SPAPIReportJob).filter(SPAPIReportJob.status == status).count() for status in statuses}
            latest_by_marketplace = {}
            for marketplace in ("US", "CA", "MX"):
                row = (
                    db.query(SPAPIReportJob)
                    .filter(SPAPIReportJob.marketplace == marketplace)
                    .order_by(SPAPIReportJob.created_at.desc())
                    .first()
                )
                latest_by_marketplace[marketplace] = SPAPIReportPipelineService._job_to_dict(row) if row else None
            return {
                "status": "OK",
                "version": SPAPIReportPipelineService.version,
                "counts": counts,
                "latest_by_marketplace": latest_by_marketplace,
                "next_step": SPAPIReportPipelineService._operational_next_step(counts),
            }
        finally:
            db.close()

    @staticmethod
    def recent_quota_limited_marketplaces(minutes: int = 60) -> dict[str, Any]:
        """Identify marketplaces that should be skipped temporarily after a 429."""
        cutoff = SPAPIReportPipelineService._now() - timedelta(minutes=max(1, minutes))
        db = SessionLocal()
        try:
            rows = (
                db.query(SPAPIReportJob)
                .filter(SPAPIReportJob.report_type == "GET_SALES_AND_TRAFFIC_REPORT")
                .filter(SPAPIReportJob.status.in_(["QUOTA_LIMITED", "ERROR"]))
                .filter(SPAPIReportJob.updated_at >= cutoff)
                .order_by(SPAPIReportJob.updated_at.desc())
                .all()
            )
            items = []
            marketplaces = set()
            for row in rows:
                message = row.error_message or ""
                response = row.response_payload or {}
                if SPAPIReportPipelineService._is_quota_error(response) or "QuotaExceeded" in message or "429" in message:
                    marketplace = row.marketplace or row.country_code
                    if marketplace:
                        marketplaces.add(str(marketplace).upper())
                    items.append(SPAPIReportPipelineService._job_to_dict(row))
            return {
                "status": "OK",
                "version": SPAPIReportPipelineService.version,
                "window_minutes": minutes,
                "marketplaces": sorted(marketplaces),
                "count": len(items),
                "items": items,
                "next_step": "Wait before requesting these marketplaces again; continue collecting already-requested jobs.",
            }
        finally:
            db.close()

    @staticmethod
    def _initial_status_for_request(requested: dict[str, Any]) -> str:
        if requested.get("status") == "OK":
            return "REQUESTED"
        if SPAPIReportPipelineService._is_quota_error(requested):
            return "QUOTA_LIMITED"
        return "ERROR"

    @staticmethod
    def _is_quota_error(payload: dict[str, Any] | None) -> bool:
        if not isinstance(payload, dict):
            return False
        if payload.get("http_status") == 429:
            return True
        text = str(payload.get("message") or payload.get("error") or payload)
        return "QuotaExceeded" in text or "quota" in text.lower() or "429" in text

    @staticmethod
    def _next_step_for_job(job: SPAPIReportJob) -> str:
        if job.status == "QUOTA_LIMITED":
            return "Amazon rate-limited this request. Wait before retrying this marketplace, but keep collecting existing jobs."
        if job.status == "REQUESTED":
            return "Poll the job until DONE, then collect it."
        if job.status == "PROCESSING":
            return "Amazon is still generating the report. Run collect-open-jobs again later."
        if job.status == "DONE":
            return "Report is ready. Run collect to download and ingest it."
        if job.status == "COLLECTED":
            return "Report has been ingested into seller_central_sales_traffic."
        return "Inspect error_message and response_payload."

    @staticmethod
    def _operational_next_step(counts: dict[str, int]) -> str:
        if counts.get("DONE", 0):
            return "Collect DONE reports now."
        if counts.get("REQUESTED", 0) or counts.get("PROCESSING", 0):
            return "Run collect-open-jobs again later; Amazon report generation is asynchronous."
        if counts.get("QUOTA_LIMITED", 0):
            return "Wait for Amazon quota to reset before requesting more reports."
        return "No open jobs. Request a new Sales & Traffic report when ready."

    @staticmethod
    def _job_to_dict(job: SPAPIReportJob | None) -> dict[str, Any] | None:
        if not job:
            return None
        return {
            "id": job.id,
            "created_at": SPAPIReportPipelineService._dt(job.created_at),
            "updated_at": SPAPIReportPipelineService._dt(job.updated_at),
            "requested_at": SPAPIReportPipelineService._dt(job.requested_at),
            "completed_at": SPAPIReportPipelineService._dt(job.completed_at),
            "report_type": job.report_type,
            "report_id": job.report_id,
            "report_document_id": job.report_document_id,
            "status": job.status,
            "processing_status": job.processing_status,
            "marketplace": job.marketplace,
            "marketplace_id": job.marketplace_id,
            "country_code": job.country_code,
            "currency": job.currency,
            "profile_id": job.profile_id,
            "start_date": str(job.start_date) if job.start_date else None,
            "end_date": str(job.end_date) if job.end_date else None,
            "asin_granularity": job.asin_granularity,
            "date_granularity": job.date_granularity,
            "request_payload": job.request_payload,
            "response_payload": job.response_payload,
            "collect_result": job.collect_result,
            "error_message": job.error_message,
        }

    @staticmethod
    def _parse_date(value: str | None):
        if not value:
            return None
        text = str(value).strip()
        # Accept API-friendly YYYY-MM-DD, Swagger/browser MM/DD/YYYY, and ISO timestamps.
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except Exception:
            pass
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(text[:10], fmt).date()
            except Exception:
                continue
        return None

    @staticmethod
    def _normalize_marketplace(value: str | None) -> str | None:
        if not value:
            return None
        text = str(value).strip()
        upper = text.upper()
        if upper in {"US", "USA", "ATVPDKIKX0DER", "AMAZON.COM"}:
            return "US"
        if upper in {"CA", "CANADA", "A2EUQ1WTGCTBG2", "AMAZON.CA"}:
            return "CA"
        if upper in {"MX", "MEXICO", "A1AM78C64UM0Y8", "AMAZON.COM.MX"}:
            return "MX"
        return text

    @staticmethod
    def _now():
        return datetime.now(timezone.utc)

    @staticmethod
    def _dt(value):
        return value.isoformat() if value else None
