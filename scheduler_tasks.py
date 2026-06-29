from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler

from database import SessionLocal
from models import ScheduledReportJob
from amazon_ads import create_report
from dashboard import save_dashboard_from_reports
from marketplace_profiles import list_marketplace_profiles


def scheduled_amazon_ads_collection():
    """
    Business OS v3.3.3

    Create Sponsored Products reports for every active marketplace profile
    and store marketplace context on each ScheduledReportJob.
    """
    try:
        print("Starting scheduled multi-market Amazon Ads report creation...")

        profiles_response = list_marketplace_profiles(active_only=True)
        profiles = profiles_response.get("items", [])

        if not profiles:
            print("No active marketplace profiles found. Scheduled report creation skipped.")
            return {
                "status": "SKIPPED",
                "message": "No active marketplace profiles found.",
                "profiles_processed": 0,
                "jobs_created": 0,
            }

        print(f"Found {len(profiles)} active marketplace profile(s).")

        db = SessionLocal()
        jobs_created = []
        failed_profiles = []

        try:
            for profile in profiles:
                country_code = profile.get("country_code")
                profile_id = profile.get("profile_id")
                marketplace = profile.get("marketplace")
                currency = profile.get("currency")

                print(
                    "Creating scheduled reports for "
                    f"country_code={country_code}, "
                    f"marketplace={marketplace}, "
                    f"profile_id={profile_id}"
                )

                try:
                    campaign_report = create_report(
                        "campaigns",
                        country_code=country_code,
                        profile_id=profile_id,
                    )

                    search_report = create_report(
                        "search_terms",
                        country_code=country_code,
                        profile_id=profile_id,
                    )

                    campaign_id = campaign_report.get("reportId")
                    search_id = search_report.get("reportId")

                    job = ScheduledReportJob(
                        date=date.today(),
                        profile_id=str(profile_id) if profile_id else None,
                        country_code=str(country_code).upper() if country_code else None,
                        marketplace=marketplace,
                        currency=currency,
                        campaign_report_id=campaign_id,
                        search_term_report_id=search_id,
                        status="PENDING",
                    )

                    db.add(job)
                    db.commit()
                    db.refresh(job)

                    jobs_created.append(
                        {
                            "job_id": job.id,
                            "country_code": country_code,
                            "marketplace": marketplace,
                            "currency": currency,
                            "profile_id": profile_id,
                            "campaign_report_id": campaign_id,
                            "search_term_report_id": search_id,
                        }
                    )

                    print(
                        "Scheduled reports created:",
                        f"job_id={job.id}",
                        f"country_code={country_code}",
                        f"campaign_report_id={campaign_id}",
                        f"search_term_report_id={search_id}",
                    )

                except Exception as profile_error:
                    db.rollback()

                    failed_profiles.append(
                        {
                            "country_code": country_code,
                            "marketplace": marketplace,
                            "profile_id": profile_id,
                            "error": str(profile_error),
                        }
                    )

                    print(
                        "Scheduled report creation failed for "
                        f"country_code={country_code}, "
                        f"profile_id={profile_id}: {profile_error}"
                    )

        finally:
            db.close()

        status = "OK" if not failed_profiles else "PARTIAL_SUCCESS"

        result = {
            "status": status,
            "message": "Scheduled multi-market Amazon Ads report creation completed.",
            "profiles_processed": len(profiles),
            "jobs_created": len(jobs_created),
            "failed_profiles": len(failed_profiles),
            "jobs": jobs_created,
            "failures": failed_profiles,
        }

        print("Scheduled multi-market report creation result:", result)
        return result

    except Exception as e:
        print("Scheduled collection failed:", str(e))
        return {
            "status": "ERROR",
            "message": "Scheduled multi-market Amazon Ads report creation failed.",
            "error": str(e),
        }


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

        results = []

        for job in jobs:
            result = save_dashboard_from_reports(
                job.campaign_report_id,
                job.search_term_report_id,
                profile_id=job.profile_id,
                country_code=job.country_code,
                marketplace=job.marketplace,
                currency=job.currency,
            )

            results.append(
                {
                    "job_id": job.id,
                    "country_code": job.country_code,
                    "marketplace": job.marketplace,
                    "profile_id": job.profile_id,
                    "result": result,
                }
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

        return {
            "status": "OK",
            "message": "Scheduled dashboard collection checked pending jobs.",
            "jobs_checked": len(jobs),
            "results": results,
        }

    except Exception as e:
        print("Scheduled dashboard collection failed:", str(e))
        return {
            "status": "ERROR",
            "message": "Scheduled dashboard collection failed.",
            "error": str(e),
        }


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
