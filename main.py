from fastapi import FastAPI

from database import engine
from models import Base
from routes_dashboard import router as dashboard_router
from routes_reports import router as reports_router
from routes_scheduler import router as scheduler_router
from scheduler_tasks import start_scheduler
from routes_recommendations import router as recommendations_router

app = FastAPI(title="Business OS API")

Base.metadata.create_all(bind=engine)

app.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(reports_router, prefix="/reports", tags=["Reports"])
app.include_router(scheduler_router, prefix="/scheduler", tags=["Scheduler"])
app.include_router(recommendations_router, prefix="/recommendations", tags=["Recommendations"])


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
