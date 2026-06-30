from fastapi import FastAPI

from database import engine
from models import Base
from execution_models import ExecutionJob, ExecutionResult
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
from routes_decision_history import router as decision_history_router
from routes_decision_metrics import router as decision_metrics_router
from routes_execution import router as execution_router
from routes_learning import router as learning_router
from routes_forecasting import router as forecasting_router
from routes_marketplace_profiles import router as marketplace_profiles_router
from routes_profiles import router as profiles_router
from routes_admin import router as admin_router
from routes_gpt import router as gpt_router
from routes_execution_v34 import router as execution_v34_router
from routes_campaign_identity import router as campaign_identity_router
from routes_execution_audit import router as execution_audit_router
from routes_execution_batch import router as execution_batch_router


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
app.include_router(decision_history_router, prefix="/business-os/decision-history", tags=["Business OS"])
app.include_router(decision_metrics_router, prefix="/business-os/decision-metrics", tags=["Business OS"])
app.include_router(execution_router, prefix="/business-os", tags=["Business OS Execution"])
app.include_router(execution_v34_router, prefix="/business-os", tags=["Business OS Execution v3.4"])
app.include_router(learning_router, prefix="/business-os/learning", tags=["Business OS Learning"])
app.include_router(forecasting_router, prefix="/business-os", tags=["Business OS Forecasting"])
app.include_router(marketplace_profiles_router, prefix="/business-os", tags=["Business OS Marketplace Profiles"])
app.include_router(profiles_router, prefix="/profiles", tags=["Amazon Ads Profiles"])
app.include_router(admin_router, prefix="/admin", tags=["Admin"])
app.include_router(gpt_router, prefix="/gpt", tags=["GPT Optimized"])
app.include_router(campaign_identity_router, prefix="/business-os", tags=["Business OS Campaign Identity"])
app.include_router(execution_audit_router, prefix="/business-os", tags=["Business OS Execution Audit"])


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
