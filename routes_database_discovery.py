"""Executive Brain v2.1.2 — Database Discovery routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from business_os.platform.discovery.service import DatabaseDiscoveryService

router = APIRouter()


@router.get("/discovery/database/overview")
def discovery_database_overview(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return DatabaseDiscoveryService.overview()


@router.get("/discovery/database/focus-profile")
def discovery_database_focus_profile(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return DatabaseDiscoveryService.focus_profile()


@router.get("/discovery/database/table/{table_name}")
def discovery_database_table(
    table_name: str,
    sample_limit: int = 5,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return DatabaseDiscoveryService.table_profile(table_name=table_name, sample_limit=sample_limit)


@router.get("/discovery/database/relationships")
def discovery_database_relationships(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return DatabaseDiscoveryService.relationship_hypotheses()


@router.get("/discovery/database/linking-diagnostics")
def discovery_database_linking_diagnostics(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return DatabaseDiscoveryService.linking_diagnostics()


@router.get("/discovery/database/amazon-scope")
def discovery_database_amazon_scope(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return DatabaseDiscoveryService.amazon_scope()
