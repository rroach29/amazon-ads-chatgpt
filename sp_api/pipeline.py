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

from datetime import datetime, timezone
from typing import Any

from database import SessionLocal
from models import SPAPIReportJob, SellerCentralSalesTraffic
from sp_api.client import SPAPIClient, SPAPIConfig
from sp_api.sales_traffic import SalesTrafficIngestionService


class SPAPIReportPipelineService:
    version = "8.9"

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
        client = SPAPIClient(SPAPIConfig.from_env(marketplace))
        requested = client.request_sales_and_traffic_report(
            start_date=start_date,
            end_date=end_date,
            marketplace_id=marketplace_id,
            asin_granularity=asin_granularity,
            date_granularity=date_granularity,
        )
        db = SessionLocal()
        try:
            job = SPAPIReportJob(
                report_type="GET_SALES_AND_TRAFFIC_REPORT",
                requested_at=SPAPIReportPipelineService._now(),
                status="REQUESTED" if requested.get("status") == "OK" else "ERROR",
                marketplace=marketplace,
                marketplace_id=marketplace_id or client.config.marketplace_id,
                country_code=(country_code or marketplace or "").upper() or None,
                currency=currency,
                profile_id=profile_id,
                start_date=SPAPIReportPipelineService._parse_date(start_date),
                end_date=SPAPIReportPipelineService._parse_date(end_date),
                asin_granularity=asin_granularity,
                date_granularity=date_granularity,
                request_payload={
                    "start_date": start_date,
                    "end_date": end_date,
                    "marketplace": marketplace,
                    "marketplace_id": marketplace_id or client.config.marketplace_id,
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
                "next_step": "Poll the job until DONE, then collect it.",
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
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except Exception:
            return None

    @staticmethod
    def _now():
        return datetime.now(timezone.utc)

    @staticmethod
    def _dt(value):
        return value.isoformat() if value else None
