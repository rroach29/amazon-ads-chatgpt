"""Business OS v0.6.2 — Product Workspace routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from business_os.product_workspace.service import ProductWorkspaceService

router = APIRouter()


@router.get("/product-workspace/portfolio")
def product_workspace_portfolio(
    limit: int = 250,
    query: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ProductWorkspaceService.portfolio(limit=limit, query=query)


@router.get("/product-workspace/products/{master_product_id}")
def product_workspace_detail(
    master_product_id: str,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ProductWorkspaceService.workspace(master_product_id)


@router.get("/product-workspace/products/{master_product_id}/decisions")
def product_workspace_decisions(
    master_product_id: str,
    status: str = "Pending",
    limit: int = 100,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ProductWorkspaceService.product_decisions(
        master_product_id=master_product_id,
        status=status,
        limit=limit,
    )


@router.get("/product-workspace/products/{master_product_id}/execution")
def product_workspace_execution(
    master_product_id: str,
    limit: int = 100,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ProductWorkspaceService.product_execution(
        master_product_id=master_product_id,
        limit=limit,
    )
