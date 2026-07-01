from fastapi import FastAPI

from database import engine
from models import Base
from execution_models import ExecutionJob, ExecutionResult
from business_registry.models import MasterProduct, ProductChannel, BusinessEvent, ProductScore
from business_os.executive.genome.models import ProductGenome
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
from routes_report_pipeline import router as report_pipeline_router
from routes_data_context import router as data_context_router
from routes_analytics_health import router as analytics_health_router
from routes_business_plans import router as business_plans_router
from routes_mission_control import router as mission_control_router
from routes_optimization import router as optimization_router
from routes_outcomes import router as outcomes_router
from routes_knowledge_graph import router as knowledge_graph_router
from routes_budget_intelligence import router as budget_intelligence_router
from routes_executive import router as executive_router
from routes_domain import router as domain_router
from routes_diagnostics import router as diagnostics_router
from routes_planning import router as planning_router
from routes_provenance import router as provenance_router
from routes_profit_intelligence import router as profit_intelligence_router
from routes_revenue_intelligence import router as revenue_intelligence_router
from routes_product_intelligence import router as product_intelligence_router
from routes_sp_api import router as sp_api_router
from routes_business_registry import router as business_registry_router
from routes_registry_integration import router as registry_integration_router
from routes_platform import router as platform_router
from routes_product_genome import router as product_genome_router
from routes_registry_linking import router as registry_linking_router
from routes_database_discovery import router as database_discovery_router


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
app.include_router(execution_batch_router, prefix="/business-os", tags=["Business OS Execution Batch"])
app.include_router(report_pipeline_router, prefix="/business-os", tags=["Business OS Report Pipeline"])
app.include_router(data_context_router, prefix="/business-os", tags=["Business OS Data Context"])
app.include_router(analytics_health_router, prefix="/business-os", tags=["Business OS Analytics Health"])
app.include_router(business_plans_router, prefix="/business-os", tags=["Business OS Plans"])
app.include_router(mission_control_router, prefix="/business-os", tags=["Business OS Mission Control"])
app.include_router(optimization_router, prefix="/business-os", tags=["Business OS Optimization Platform"])
app.include_router(outcomes_router, prefix="/business-os", tags=["Business OS Outcome Intelligence"])
app.include_router(knowledge_graph_router, prefix="/business-os", tags=["Business OS Knowledge Graph"])
app.include_router(budget_intelligence_router, prefix="/business-os", tags=["Business OS Budget Intelligence"])
app.include_router(executive_router, prefix="/business-os", tags=["Business OS Executive AI"])
app.include_router(domain_router, prefix="/business-os", tags=["Business OS Domain Models"])
app.include_router(diagnostics_router, prefix="/business-os", tags=["Business OS Diagnostics"])
app.include_router(planning_router, prefix="/business-os", tags=["Business OS Executive Planning"])
app.include_router(provenance_router, prefix="/business-os", tags=["Business OS Optimizer Manifests"])
app.include_router(profit_intelligence_router, prefix="/business-os", tags=["Business OS Profit Intelligence"])
app.include_router(revenue_intelligence_router, prefix="/business-os", tags=["Business OS Revenue Intelligence"])
app.include_router(product_intelligence_router, prefix="/business-os", tags=["Business OS Product Intelligence"])
app.include_router(sp_api_router, prefix="/business-os", tags=["Business OS SP-API"] )
app.include_router(business_registry_router, prefix="/business-os", tags=["Business OS Registry"])
app.include_router(registry_integration_router, prefix="/business-os", tags=["Business OS Registry Integration"])
app.include_router(platform_router, prefix="/business-os", tags=["Business OS Platform"])
app.include_router(product_genome_router, prefix="/business-os", tags=["Executive Brain Product Genome"])
app.include_router(registry_linking_router, prefix="/business-os", tags=["Business OS Registry Linking"])
app.include_router(database_discovery_router, prefix="/business-os", tags=["Business OS Database Discovery"])


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
