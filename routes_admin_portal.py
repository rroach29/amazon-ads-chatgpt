"""Business OS v3.0 — Admin Portal routes."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from business_os.ui.service import AdminPortalService

router = APIRouter()


@router.get("/ui", response_class=HTMLResponse)
def business_os_ui_home():
    return AdminPortalService.home()


@router.get("/ui/products", response_class=HTMLResponse)
def business_os_ui_products(
    q: str | None = None,
    active: bool | None = None,
    limit: int = 100,
):
    return AdminPortalService.products(q=q, active=active, limit=limit)


@router.get("/ui/products/{master_product_id}", response_class=HTMLResponse)
def business_os_ui_product_detail(master_product_id: str):
    return AdminPortalService.product_detail(master_product_id)


@router.get("/ui/channels", response_class=HTMLResponse)
def business_os_ui_channels(
    mapped: bool | None = None,
    limit: int = 250,
):
    return AdminPortalService.channels(mapped=mapped, limit=limit)


@router.get("/ui/genomes", response_class=HTMLResponse)
def business_os_ui_genomes(limit: int = 100):
    return AdminPortalService.genomes(limit=limit)


@router.get("/ui/events", response_class=HTMLResponse)
def business_os_ui_events(limit: int = 100):
    return AdminPortalService.events(limit=limit)
