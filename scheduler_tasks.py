from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler

from database import SessionLocal
from models import ScheduledReportJob
from amazon_ads import create_report
from dashboard import save_dashboard_from_reports


def scheduled_amazon_ads_collection():
    try:
        print("Starting scheduled Amazon Ads report creation...")

        campaign_report = create_report("campaigns")
        search_report = create_report("search_terms")

        campaign_id = campaign_report.get("reportId")
        search_id = search_report.get("reportId")

        db = SessionLocal()

        job = ScheduledReportJob(
            date=date.today(),
            campaign_report_id=campaign_id,
            search_term_report_id=search_id,
            status="PENDING",
        )

        db.add(job)
        db.commit()
        db.close()

        print("Scheduled reports created:", campaign_id, search_id)

    except Exception as e:
        print("Scheduled collection failed:", str(e))


def scheduled_dashboard_collection():
    try:
        print("Checking pending scheduled report jobs...")

        db = SessionLocal()

        jobs = (
            db.query(ScheduledReportJob)
            .filter(ScheduledReportJob.status == "PENDING")
            .all()
        )

        db.close()

        for job in jobs:
            result = save_dashboard_from_reports(
                job.campaign_report_id,
                job.search_term_report_id,
            )

            if result.get("status") == "OK":
                db = SessionLocal()
                existing_job = db.query(ScheduledReportJob).filter(ScheduledReportJob.id == job.id).first()
                existing_job.status = "COMPLETED"
                db.commit()
                db.close()

                print("Dashboard saved for job:", job.id)

            else:
                print("Job still pending:", job.id, result)

    except Exception as e:
        print("Scheduled dashboard collection failed:", str(e))


def start_scheduler():
    scheduler = BackgroundScheduler(timezone="America/Regina")

    scheduler.add_job(
        scheduled_amazon_ads_collection,
        "cron",
        hour=6,
        minute=0,
        id="daily_amazon_ads_report_creation",
        replace_existing=True,
    )

    scheduler.add_job(
        scheduled_dashboard_collection,
        "interval",
        minutes=10,
        id="scheduled_dashboard_collection",
        replace_existing=True,
    )

    scheduler.start()
