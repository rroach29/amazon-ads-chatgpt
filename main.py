from fastapi import FastAPI

from database import engine
from models import Base
from routes_dashboard import router as dashboard_router
from routes_reports import router as reports_router
from routes_scheduler import router as scheduler_router
from scheduler_tasks import start_scheduler
from routes_recommendations import router as recommendations_router
from routes_optimization_queue import router as optimization_queue_router
from routes_business_context import router as business_context_router
from routes_trends import router as trends_router
from routes_morning_brief import router as morning_brief_router
from routes_intelligence import router as intelligence_router
from routes_root_cause import router as root_cause_router
from routes_decisions import router as decisions_router

app = FastAPI(title="Business OS API")

Base.metadata.create_all(bind=engine)

app.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(reports_router, prefix="/reports", tags=["Reports"])
app.include_router(scheduler_router, prefix="/scheduler", tags=["Scheduler"])
app.include_router(recommendations_router, prefix="/recommendations", tags=["Recommendations"])
app.include_router(optimization_queue_router,prefix="/optimization-queue",tags=["Optimization Queue"])
app.include_router(business_context_router, prefix="/business-os", tags=["Business OS"])
app.include_router(trends_router, prefix="/business-os/trends", tags=["Business OS"])
app.include_router(morning_brief_router, prefix="/business-os/morning-brief", tags=["Business OS"])
app.include_router(intelligence_router, prefix="/business-os/intelligence", tags=["Business OS"])
app.include_router(root_cause_router, prefix="/business-os/root-cause", tags=["Business OS"])
app.include_router(decisions_router, prefix="/business-os/decisions", tags=["Business OS"])

@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "Business OS API is running",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


start_scheduler()
