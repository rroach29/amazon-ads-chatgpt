"""Business OS v8.9 — SP-API routes and Seller Central data pipeline."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header

from auth import verify_key
from sp_api import SPAPIClient, SPAPIConfig, SalesTrafficIngestionService, SPAPIReportPipelineService

router = APIRouter()


def _client(marketplace: str | None = None) -> SPAPIClient:
    return SPAPIClient(SPAPIConfig.from_env(marketplace))


@router.get("/sp-api/status")
def business_os_sp_api_status(
    marketplace: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return _client(marketplace).diagnostics()


@router.get("/sp-api/auth-test")
def business_os_sp_api_auth_test(
    marketplace: str | None = None,
    include_sp_api_call: bool = False,
    x_api_key: str = Header(...),
):
    """Verify LWA token exchange and optionally run a signed SP-API test call."""
    verify_key(x_api_key)
    return _client(marketplace).auth_test(include_sp_api_call=include_sp_api_call)


@router.get("/sp-api/marketplaces")
def business_os_sp_api_marketplaces(
    marketplace: str | None = None,
    x_api_key: str = Header(...),
):
    """Call SP-API Sellers API to verify SigV4 + seller authorization."""
    verify_key(x_api_key)
    return _client(marketplace).get_marketplace_participations()


@router.get("/sp-api/pipeline/diagnostics")
def business_os_sp_api_pipeline_diagnostics(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return SPAPIReportPipelineService.diagnostics()


@router.get("/sp-api/pipeline/jobs")
def business_os_sp_api_pipeline_jobs(
    limit: int = 25,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return SPAPIReportPipelineService.list_jobs(limit=limit)


@router.get("/sp-api/pipeline/jobs/{job_id}")
def business_os_sp_api_pipeline_job(
    job_id: int,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return SPAPIReportPipelineService.get_job(job_id)


@router.post("/sp-api/pipeline/sales-traffic/request")
def business_os_sp_api_pipeline_request_sales_traffic(
    start_date: str,
    end_date: str,
    marketplace: str | None = None,
    marketplace_id: str | None = None,
    country_code: str | None = None,
    currency: str | None = None,
    profile_id: str | None = None,
    asin_granularity: str = "CHILD",
    date_granularity: str = "DAY",
    x_api_key: str = Header(...),
):
    """Request and persist a Sales & Traffic report job."""
    verify_key(x_api_key)
    return SPAPIReportPipelineService.request_sales_traffic_job(
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


@router.post("/sp-api/pipeline/jobs/{job_id}/poll")
def business_os_sp_api_pipeline_poll_job(
    job_id: int,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return SPAPIReportPipelineService.poll_job(job_id)


@router.post("/sp-api/pipeline/jobs/{job_id}/collect")
def business_os_sp_api_pipeline_collect_job(
    job_id: int,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return SPAPIReportPipelineService.collect_job(job_id)


@router.post("/sp-api/pipeline/sales-traffic/run")
def business_os_sp_api_pipeline_run_sales_traffic(
    start_date: str,
    end_date: str,
    marketplace: str | None = None,
    marketplace_id: str | None = None,
    country_code: str | None = None,
    currency: str | None = None,
    profile_id: str | None = None,
    asin_granularity: str = "CHILD",
    date_granularity: str = "DAY",
    x_api_key: str = Header(...),
):
    """Request + initial poll for Sales & Traffic report. Collect when DONE."""
    verify_key(x_api_key)
    return SPAPIReportPipelineService.run_once(
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


# Backward-compatible v8.8.1 endpoints.
@router.post("/sp-api/reports/sales-traffic/request")
def business_os_sp_api_request_sales_traffic_report(
    start_date: str,
    end_date: str,
    marketplace: str | None = None,
    marketplace_id: str | None = None,
    asin_granularity: str = "CHILD",
    date_granularity: str = "DAY",
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    client = _client(marketplace)
    return client.request_sales_and_traffic_report(
        start_date=start_date,
        end_date=end_date,
        marketplace_id=marketplace_id,
        asin_granularity=asin_granularity,
        date_granularity=date_granularity,
    )


@router.get("/sp-api/reports/{report_id}/status")
def business_os_sp_api_report_status(
    report_id: str,
    marketplace: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return _client(marketplace).get_report(report_id)


@router.post("/sp-api/reports/{report_id}/collect")
def business_os_sp_api_collect_report(
    report_id: str,
    marketplace: str | None = None,
    country_code: str | None = None,
    currency: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    client = _client(marketplace)
    report = client.get_report(report_id)
    if report.get("status") != "OK":
        return report
    report_payload = report.get("response", {})
    document_id = report_payload.get("reportDocumentId")
    processing_status = report_payload.get("processingStatus")
    if processing_status and processing_status != "DONE":
        return {"status": "PENDING", "processing_status": processing_status, "report": report_payload}
    if not document_id:
        return {"status": "ERROR", "message": "Report is DONE but reportDocumentId is missing.", "report": report_payload}
    document = client.get_report_document(document_id)
    if document.get("status") != "OK":
        return document
    downloaded = client.download_report_document(document.get("response", {}))
    if downloaded.get("status") != "OK":
        return downloaded
    return SalesTrafficIngestionService.ingest_payload(
        downloaded.get("document"),
        country_code=country_code,
        marketplace=marketplace,
        marketplace_id=client.config.marketplace_id,
        currency=currency,
        profile_id=profile_id,
    )


@router.post("/sp-api/reports/sales-traffic/run")
def business_os_sp_api_run_sales_traffic_report(
    start_date: str,
    end_date: str,
    marketplace: str | None = None,
    marketplace_id: str | None = None,
    asin_granularity: str = "CHILD",
    date_granularity: str = "DAY",
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    client = _client(marketplace)
    requested = client.request_sales_and_traffic_report(
        start_date=start_date,
        end_date=end_date,
        marketplace_id=marketplace_id,
        asin_granularity=asin_granularity,
        date_granularity=date_granularity,
    )
    if requested.get("status") != "OK":
        return requested
    response = requested.get("response", {})
    return {
        "status": "REQUESTED",
        "report_id": response.get("reportId"),
        "response": response,
        "next_step": "Poll GET /business-os/sp-api/reports/{report_id}/status until processingStatus is DONE, then POST collect.",
    }


@router.post("/sp-api/sales-traffic/ingest")
def business_os_sp_api_ingest_sales_traffic_payload(
    payload: dict[str, Any] | list[Any],
    country_code: str | None = None,
    marketplace: str | None = None,
    marketplace_id: str | None = None,
    currency: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    """Manual fallback ingestion endpoint for Sales & Traffic JSON payloads."""
    verify_key(x_api_key)
    return SalesTrafficIngestionService.ingest_payload(
        payload,
        country_code=country_code,
        marketplace=marketplace,
        marketplace_id=marketplace_id,
        currency=currency,
        profile_id=profile_id,
    )
