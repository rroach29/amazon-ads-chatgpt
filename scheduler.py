"""
Business OS v3.9.0
Scheduler

Runs:
- daily report creation
- automatic polling/collection of ready reports

Dayparting support:
- not active yet
- v3.9.1 will add hourly report creation after daily pipeline is stable
"""

from apscheduler.schedulers.background import BackgroundScheduler

from report_pipeline import (
    create_daily_report_jobs,
    collect_ready_report_jobs,
)


def scheduled_daily_report_creation():
    try:
        print("Business OS v3.9.0: Creating daily marketplace report jobs...")
        result = create_daily_report_jobs()
        print("Daily report creation result:", result)
        return result
    except Exception as exc:
        print("Daily report creation failed:", str(exc))
        return {
            "status": "ERROR",
            "message": "Daily report creation failed.",
            "error": str(exc),
        }


def scheduled_report_collection():
    try:
        print("Business OS v3.9.0: Checking pending report jobs for completed reports...")
        result = collect_ready_report_jobs(limit=20)
        print("Report collection result:", result)
        return result
    except Exception as exc:
        print("Scheduled report collection failed:", str(exc))
        return {
            "status": "ERROR",
            "message": "Scheduled report collection failed.",
            "error": str(exc),
        }


# Backward-compatible function names used by older routes.
def scheduled_amazon_ads_collection():
    return scheduled_daily_report_creation()


def scheduled_dashboard_collection():
    return scheduled_report_collection()


def start_scheduler():
    scheduler = BackgroundScheduler(timezone="America/Regina")

    scheduler.add_job(
        scheduled_daily_report_creation,
        "cron",
        hour=6,
        minute=0,
        id="daily_marketplace_report_creation",
        replace_existing=True,
    )

    # Poll every 10 minutes. Amazon reports are asynchronous.
    scheduler.add_job(
        scheduled_report_collection,
        "interval",
        minutes=10,
        id="daily_marketplace_report_collection",
        replace_existing=True,
    )

    scheduler.start()
    print("Business OS scheduler started: daily reports + auto collection.")
