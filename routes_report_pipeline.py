from fastapi import APIRouter, Header

from auth import verify_key
from report_pipeline import (
    create_daily_report_jobs,
    collect_ready_report_jobs,
    run_report_pipeline_once,
    list_report_jobs,
    dayparting_foundation_status,
)

router = APIRouter()


@router.post("/reports/create-daily")
def create_daily_reports(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return create_daily_report_jobs()


@router.post("/reports/collect-ready")
def collect_ready_reports(
    limit: int = 20,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return collect_ready_report_jobs(limit=limit)


@router.post("/reports/run-pipeline")
def run_pipeline_once(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return run_report_pipeline_once()


@router.get("/reports/jobs")
def report_jobs(
    status: str | None = None,
    limit: int = 50,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return list_report_jobs(status=status, limit=limit)


@router.get("/dayparting/status")
def dayparting_status(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return dayparting_foundation_status()
