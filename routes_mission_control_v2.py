"""Business OS v0.4.2 — Mission Control v2 routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from business_os.mission_control_v2.service import MissionControlV2Service

router = APIRouter()


@router.get("/mission-control-v2/summary")
def mission_control_v2_summary(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return MissionControlV2Service.summary()


@router.get("/mission-control-v2/queue")
def mission_control_v2_queue(
    status: str = "Pending",
    limit: int = 100,
    include_setup: bool = False,
    source: str | None = None,
    category: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return MissionControlV2Service.executive_queue(
        status=status,
        limit=limit,
        include_setup=include_setup,
        source=source,
        category=category,
    )


@router.get("/mission-control-v2/search-decisions")
def mission_control_v2_search_decisions(
    limit: int = 100,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return MissionControlV2Service.search_decisions(limit=limit)


@router.get("/mission-control-v2/advertising-decisions")
def mission_control_v2_advertising_decisions(
    limit: int = 100,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return MissionControlV2Service.advertising_decisions(limit=limit)


@router.post("/mission-control-v2/cleanup-setup-noise")
def mission_control_v2_cleanup_setup_noise(
    dry_run: bool = True,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return MissionControlV2Service.cleanup_setup_noise(dry_run=dry_run)
