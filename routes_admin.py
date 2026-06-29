from fastapi import APIRouter, Header

from auth import verify_key
from admin_migrations import (
    get_database_schema,
    get_database_version,
    get_daily_dashboard_indexes,
    migrate_v3_3_3_marketplace_storage,
    repair_daily_dashboard_marketplace_index,
    rollback_v3_3_3_marketplace_storage,
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


@router.get("/daily-dashboard-indexes")
def admin_daily_dashboard_indexes(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return get_daily_dashboard_indexes()


@router.post("/migrate/v3.3.3")
def admin_migrate_v3_3_3(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return migrate_v3_3_3_marketplace_storage()


@router.post("/repair/daily-dashboard-index")
def admin_repair_daily_dashboard_index(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return repair_daily_dashboard_marketplace_index()


@router.post("/rollback/v3.3.3")
def admin_rollback_v3_3_3(
    confirm: bool = False,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return rollback_v3_3_3_marketplace_storage(confirm=confirm)
