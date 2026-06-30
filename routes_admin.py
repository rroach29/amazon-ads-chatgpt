from fastapi import APIRouter, Header

from auth import verify_key
from admin_migrations import (
    get_database_schema,
    get_database_version,
    migrate_v3_4_1_execution_framework,
    migrate_v7_0_business_knowledge_graph,
    migrate_v8_6_revenue_intelligence,
)

router = APIRouter()


@router.get("/schema")
def admin_schema(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return get_database_schema()


@router.get("/database-version")
def admin_database_version(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return get_database_version()


@router.post("/migrate/v3.4.1")
def admin_migrate_v3_4_1(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return migrate_v3_4_1_execution_framework()


@router.post("/migrate/v7.0")
def admin_migrate_v7_0(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return migrate_v7_0_business_knowledge_graph()



@router.post("/migrate/v8.6")
def admin_migrate_v8_6(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return migrate_v8_6_revenue_intelligence()
