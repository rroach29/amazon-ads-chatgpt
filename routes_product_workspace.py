"""Business OS v0.6.6 — Product Workspace routes.

Adds a fast default portfolio response so the Product Dashboard can load quickly.
Full product metrics still load on the product detail endpoint.
"""

from fastapi import APIRouter, Header
from sqlalchemy import desc

from auth import verify_key
from database import SessionLocal
from business_registry.models import MasterProduct, ProductChannel
from business_os.executive.genome.models import ProductGenome
from business_os.execution_framework.models import ExecutionPlan
from business_os.mission_control.models import MissionControlDecision
from business_os.product_workspace.service import ProductWorkspaceService

router = APIRouter()


@router.get("/product-workspace/portfolio")
def product_workspace_portfolio(
    limit: int = 250,
    query: str | None = None,
    fast: bool = True,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    if fast:
        return _fast_portfolio(limit=limit, query=query)
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


def _fast_portfolio(limit: int = 250, query: str | None = None):
    db = SessionLocal()
    try:
        q = db.query(MasterProduct).filter(MasterProduct.active == True)
        if query:
            pattern = f"%{query}%"
            q = q.filter(
                (MasterProduct.name.ilike(pattern))
                | (MasterProduct.primary_sku.ilike(pattern))
                | (MasterProduct.brand.ilike(pattern))
                | (MasterProduct.product_family.ilike(pattern))
            )

        products = q.order_by(MasterProduct.name).limit(max(1, min(limit, 500))).all()
        product_ids = [p.master_product_id for p in products]

        channels_by_product = {product_id: [] for product_id in product_ids}
        if product_ids:
            channels = db.query(ProductChannel).filter(ProductChannel.master_product_id.in_(product_ids)).all()
            for channel in channels:
                channels_by_product.setdefault(channel.master_product_id, []).append(channel)

        pending_counts = {product_id: 0 for product_id in product_ids}
        if product_ids:
            pending_rows = db.query(MissionControlDecision.master_product_id).filter(
                MissionControlDecision.master_product_id.in_(product_ids),
                MissionControlDecision.status == "Pending",
            ).all()
            for row in pending_rows:
                pending_counts[row[0]] = pending_counts.get(row[0], 0) + 1

        execution_counts = {product_id: 0 for product_id in product_ids}
        if product_ids:
            plan_rows = db.query(ExecutionPlan.master_product_id).filter(ExecutionPlan.master_product_id.in_(product_ids)).all()
            for row in plan_rows:
                execution_counts[row[0]] = execution_counts.get(row[0], 0) + 1

        genome_by_product = {}
        if product_ids:
            genomes = db.query(ProductGenome).filter(ProductGenome.master_product_id.in_(product_ids)).all()
            for genome in genomes:
                genome_by_product[genome.master_product_id] = genome

        items = []
        for product in products:
            channels = channels_by_product.get(product.master_product_id, [])
            channel_names = sorted(set([_safe_get(c, "channel") for c in channels if _safe_get(c, "channel")]))
            marketplaces = sorted(set([_safe_get(c, "marketplace") for c in channels if _safe_get(c, "marketplace")]))
            genome = genome_by_product.get(product.master_product_id)
            scores = _genome_scores(genome)
            items.append({
                "master_product_id": product.master_product_id,
                "product_name": product.name,
                "brand": product.brand,
                "primary_sku": product.primary_sku,
                "product_family": product.product_family,
                "lifecycle_stage": product.lifecycle_stage,
                "status": product.status,
                "channels": channel_names,
                "marketplaces": marketplaces,
                "channel_count": len(channels),
                "health": scores.get("product_health"),
                "sales_30d": None,
                "ad_sales_30d": None,
                "organic_sales_30d": None,
                "spend_30d": None,
                "acos_pct": None,
                "tacos_pct": None,
                "paid_sales_share_pct": None,
                "open_decisions": pending_counts.get(product.master_product_id, 0),
                "execution_plans": execution_counts.get(product.master_product_id, 0),
            })

        items.sort(key=lambda item: (
            -(item.get("open_decisions") or 0),
            item.get("product_name") or "",
        ))

        return {
            "status": "OK",
            "version": "business-os-0.6.6-fast-portfolio",
            "fast": True,
            "count": len(items),
            "summary": {
                "products": len(items),
                "average_health": _average_health(items),
                "sales_30d": None,
                "ad_sales_30d": None,
                "organic_sales_30d": None,
                "spend_30d": None,
                "paid_sales_share_pct": None,
                "products_with_open_decisions": len([i for i in items if (i.get("open_decisions") or 0) > 0]),
                "total_open_decisions": sum(i.get("open_decisions") or 0 for i in items),
                "products_with_execution_plans": len([i for i in items if (i.get("execution_plans") or 0) > 0]),
                "note": "Fast portfolio omits expensive per-product metrics. Open a product for full Product Performance Mix.",
            },
            "products": items,
        }
    finally:
        db.close()


def _safe_get(obj, name, default=None):
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _genome_scores(genome):
    if not genome:
        return {}
    scores = _safe_get(genome, "scores")
    if isinstance(scores, dict):
        return {"product_health": scores.get("product_health")}
    for name in ["product_health", "health_score", "health"]:
        value = _safe_get(genome, name)
        if value is not None:
            return {"product_health": value}
    return {}


def _average_health(items):
    with_health = [item for item in items if item.get("health") is not None]
    return round(sum(item["health"] for item in with_health) / len(with_health)) if with_health else None
