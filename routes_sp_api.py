"""Business OS v8.8 — SP-API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header

from auth import verify_key
from sp_api import SPAPIClient, SPAPIConfig, SalesTrafficIngestionService

router = APIRouter()


@router.get("/sp-api/status")
def business_os_sp_api_status(
    marketplace: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    client = SPAPIClient(SPAPIConfig.from_env(marketplace))
    return client.diagnostics()


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
    client = SPAPIClient(SPAPIConfig.from_env(marketplace))
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
    client = SPAPIClient(SPAPIConfig.from_env(marketplace))
    return client.get_report(report_id)


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
    client = SPAPIClient(SPAPIConfig.from_env(marketplace))
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
    """Manual fallback ingestion endpoint.

    Useful before live SP-API credentials are fully approved: paste a Sales &
    Traffic JSON payload into Swagger and populate Revenue/Product Intelligence.
    """
    verify_key(x_api_key)
    return SalesTrafficIngestionService.ingest_payload(
        payload,
        country_code=country_code,
        marketplace=marketplace,
        marketplace_id=marketplace_id,
        currency=currency,
        profile_id=profile_id,
    )
