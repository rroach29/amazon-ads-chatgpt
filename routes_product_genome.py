"""Executive Brain v2.0 — Product Genome routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from business_os.executive.genome.service import ProductGenomeService

router = APIRouter()


@router.get("/executive/product-genomes")
def list_product_genomes(
    limit: int = 250,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ProductGenomeService.list_genomes(limit=limit)


@router.get("/executive/product-genomes/summary")
def product_genome_summary(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return ProductGenomeService.summary()


@router.get("/executive/product-genomes/{master_product_id}")
def get_product_genome(
    master_product_id: str,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ProductGenomeService.get_genome(master_product_id=master_product_id)


@router.post("/executive/product-genomes/recalculate")
def recalculate_product_genomes(
    master_product_id: str | None = None,
    limit: int = 500,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ProductGenomeService.recalculate(master_product_id=master_product_id, limit=limit)
