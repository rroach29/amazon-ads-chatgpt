"""
Business OS v3.9.0
Autonomous Report Pipeline + Dayparting-Ready Scheduler

Purpose:
- Stop treating report creation and dashboard collection as separate manual steps.
- Create daily reports for each active marketplace.
- Store report pairs as ScheduledReportJob rows.
- Poll pending jobs.
- Automatically collect completed report pairs into dashboard tables.
- Prepare architecture for future dayparting/hourly report jobs.

This module intentionally keeps hourly/dayparting as a future job type, not live yet.
"""

from datetime import date, datetime
from typing import Any

from database import SessionLocal
from models import ScheduledReportJob
from amazon_ads import create_report, get_report_status
from dashboard import save_dashboard_from_reports
from marketplace_profiles import list_marketplace_profiles


REPORT_JOB_STATUS_PENDING = "PENDING"
REPORT_JOB_STATUS_COMPLETED = "COMPLETED"
REPORT_JOB_STATUS_FAILED = "FAILED"
REPORT_JOB_STATUS_NOT_READY = "NOT_READY"


def _safe_get(data: Any, key: str, default=None):
    return data.get(key, default) if isinstance(data, dict) else default


def _normalize_report_status(response):
    if not isinstance(response, dict):
        return "UNKNOWN"

    status = response.get("status")
    if status:
        return str(status).upper()

    return "UNKNOWN"


def _create_marketplace_report_pair(profile):
    country_code = profile.get("country_code")
    profile_id = profile.get("profile_id")
    marketplace = profile.get("marketplace")
    currency = profile.get("currency")

    campaign_report = create_report(
        "campaigns",
        country_code=country_code,
        profile_id=profile_id,
    )

    search_term_report = create_report(
        "search_terms",
        country_code=country_code,
        profile_id=profile_id,
    )

    campaign_report_id = campaign_report.get("reportId")
    search_term_report_id = search_term_report.get("reportId")

    if not campaign_report_id:
        raise ValueError(f"Missing campaign report ID for {country_code}: {campaign_report}")

    if not search_term_report_id:
        raise ValueError(f"Missing search term report ID for {country_code}: {search_term_report}")

    return {
        "country_code": country_code,
        "profile_id": profile_id,
        "marketplace": marketplace,
        "currency": currency,
        "campaign_report_id": campaign_report_id,
        "search_term_report_id": search_term_report_id,
        "campaign_report_response": campaign_report,
        "search_term_report_response": search_term_report,
    }


def create_daily_report_jobs():
    """
    Create daily campaign + search-term report pairs for every active marketplace.

    This should be called once per day.
    """
    profiles_response = list_marketplace_profiles(active_only=True)
    profiles = profiles_response.get("items", [])

    if not profiles:
        return {
            "status": "SKIPPED",
            "message": "No active marketplace profiles found.",
            "profiles_processed": 0,
            "jobs_created": 0,
            "jobs": [],
            "failures": [],
        }

    db = SessionLocal()
    jobs = []
    failures = []

    try:
        for profile in profiles:
            try:
                report_pair = _create_marketplace_report_pair(profile)

                job = ScheduledReportJob(
                    date=date.today(),
                    profile_id=report_pair["profile_id"],
                    country_code=report_pair["country_code"],
                    marketplace=report_pair["marketplace"],
                    currency=report_pair["currency"],
                    campaign_report_id=report_pair["campaign_report_id"],
                    search_term_report_id=report_pair["search_term_report_id"],
                    status=REPORT_JOB_STATUS_PENDING,
                )

                db.add(job)
                db.commit()
                db.refresh(job)

                jobs.append({
                    "job_id": job.id,
                    "date": str(job.date),
                    "profile_id": job.profile_id,
                    "country_code": job.country_code,
                    "marketplace": job.marketplace,
                    "currency": job.currency,
                    "campaign_report_id": job.campaign_report_id,
                    "search_term_report_id": job.search_term_report_id,
                    "status": job.status,
                    "campaign_report_response": report_pair["campaign_report_response"],
                    "search_term_report_response": report_pair["search_term_report_response"],
                })

            except Exception as exc:
                db.rollback()
                failures.append({
                    "profile": profile,
                    "error": str(exc),
                })

        return {
            "status": "OK" if not failures else "PARTIAL_SUCCESS",
            "message": "Daily marketplace report jobs created.",
            "profiles_processed": len(profiles),
            "jobs_created": len(jobs),
            "failed_profiles": len(failures),
            "jobs": jobs,
            "failures": failures,
        }

    finally:
        db.close()


def _check_job_report_status(job):
    campaign_status = get_report_status(
        job.campaign_report_id,
        profile_id=job.profile_id,
        country_code=job.country_code,
    )

    search_term_status = get_report_status(
        job.search_term_report_id,
        profile_id=job.profile_id,
        country_code=job.country_code,
    )

    campaign_state = _normalize_report_status(campaign_status)
    search_term_state = _normalize_report_status(search_term_status)

    return {
        "campaign": {
            "report_id": job.campaign_report_id,
            "state": campaign_state,
            "response": campaign_status,
        },
        "search_term": {
            "report_id": job.search_term_report_id,
            "state": search_term_state,
            "response": search_term_status,
        },
        "both_completed": campaign_state == "COMPLETED" and search_term_state == "COMPLETED",
        "any_failed": campaign_state in ["FAILURE", "FAILED"] or search_term_state in ["FAILURE", "FAILED"],
    }


def collect_ready_report_jobs(limit=20):
    """
    Poll pending jobs and collect completed report pairs automatically.
    """
    db = SessionLocal()
    processed = []
    not_ready = []
    failed = []

    try:
        jobs = (
            db.query(ScheduledReportJob)
            .filter(ScheduledReportJob.status == REPORT_JOB_STATUS_PENDING)
            .order_by(ScheduledReportJob.created_at.asc())
            .limit(limit)
            .all()
        )

        for job in jobs:
            try:
                status_result = _check_job_report_status(job)

                if status_result["any_failed"]:
                    job.status = REPORT_JOB_STATUS_FAILED
                    db.commit()

                    failed.append({
                        "job_id": job.id,
                        "country_code": job.country_code,
                        "marketplace": job.marketplace,
                        "status": status_result,
                    })
                    continue

                if not status_result["both_completed"]:
                    not_ready.append({
                        "job_id": job.id,
                        "country_code": job.country_code,
                        "marketplace": job.marketplace,
                        "status": status_result,
                    })
                    continue

                collection_result = save_dashboard_from_reports(
                    job.campaign_report_id,
                    job.search_term_report_id,
                    country_code=job.country_code,
                    profile_id=job.profile_id,
                )

                if collection_result.get("status") == "OK":
                    job.status = REPORT_JOB_STATUS_COMPLETED
                    db.commit()

                    processed.append({
                        "job_id": job.id,
                        "country_code": job.country_code,
                        "marketplace": job.marketplace,
                        "campaign_report_id": job.campaign_report_id,
                        "search_term_report_id": job.search_term_report_id,
                        "collection_result": collection_result,
                    })
                else:
                    not_ready.append({
                        "job_id": job.id,
                        "country_code": job.country_code,
                        "marketplace": job.marketplace,
                        "status": status_result,
                        "collection_result": collection_result,
                    })

            except Exception as exc:
                db.rollback()
                failed.append({
                    "job_id": job.id,
                    "country_code": job.country_code,
                    "marketplace": job.marketplace,
                    "error": str(exc),
                })

        return {
            "status": "OK",
            "message": "Pending report jobs checked.",
            "pending_checked": len(jobs),
            "completed_collected": len(processed),
            "not_ready": len(not_ready),
            "failed": len(failed),
            "processed_jobs": processed,
            "not_ready_jobs": not_ready,
            "failed_jobs": failed,
        }

    finally:
        db.close()


def run_report_pipeline_once():
    """
    Manual one-shot endpoint:
    1. Create daily report jobs.
    2. Immediately check pending jobs.

    Newly created Amazon reports usually won't be ready immediately, but this endpoint
    gives a complete operational status in one response.
    """
    create_result = create_daily_report_jobs()
    collect_result = collect_ready_report_jobs()

    return {
        "status": "OK",
        "message": "Report pipeline triggered.",
        "create": create_result,
        "collect": collect_result,
        "note": "Amazon reports are asynchronous. If not_ready > 0, run collect again in a few minutes or let the scheduler poll automatically.",
    }


def list_report_jobs(status=None, limit=50):
    db = SessionLocal()

    try:
        query = db.query(ScheduledReportJob).order_by(ScheduledReportJob.created_at.desc())

        if status:
            query = query.filter(ScheduledReportJob.status == status)

        rows = query.limit(limit).all()

        return {
            "status": "OK",
            "count": len(rows),
            "items": [
                {
                    "job_id": row.id,
                    "date": str(row.date),
                    "profile_id": row.profile_id,
                    "country_code": row.country_code,
                    "marketplace": row.marketplace,
                    "currency": row.currency,
                    "campaign_report_id": row.campaign_report_id,
                    "search_term_report_id": row.search_term_report_id,
                    "status": row.status,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ],
        }

    finally:
        db.close()


def dayparting_foundation_status():
    """
    v3.9.0 intentionally does not create hourly reports yet.

    This endpoint documents readiness for v3.9.1/v3.10.
    """
    return {
        "status": "PLANNED",
        "phase": "dayparting_foundation",
        "current_release": "v3.9.0",
        "message": "Daily autonomous reporting is being stabilized first. Hourly report collection comes next.",
        "planned_job_types": [
            "hourly_campaign_reports",
            "hourly_search_term_reports",
            "day_of_week_hour_of_day_aggregation",
            "marketplace_specific_dayparting",
        ],
        "execution_policy": "No dayparting execution until enough hourly data is collected and analyzed.",
    }
