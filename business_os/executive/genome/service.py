"""Executive Brain v2.0 — Product Genome service."""

from __future__ import annotations

from business_os.platform.services.base import BaseService
from business_os.executive.genome.engine import ProductGenomeEngine
from business_os.executive.genome.repository import ProductGenomeRepository


class ProductGenomeService(BaseService):
    version = "executive-brain-2.0"

    @classmethod
    def recalculate(cls, master_product_id: str | None = None, limit: int = 500) -> dict:
        repo = ProductGenomeRepository()
        try:
            products = repo.master_products(limit=limit)
            if master_product_id:
                products = [p for p in products if p.master_product_id == master_product_id]

            calculated = []
            for product in products:
                genome_data = ProductGenomeEngine.calculate_for_master_product(repo, product)
                genome = repo.save_genome(genome_data)
                calculated.append(cls._genome_to_dict(genome))

            return cls.response(
                payload={
                    "calculated_count": len(calculated),
                    "genomes": calculated[:100],
                    "note": "Product Genome v2.0 calculates executive profiles from Registry-linked Seller Central and Amazon Ads data.",
                }
            )
        finally:
            repo.close()

    @classmethod
    def list_genomes(cls, limit: int = 250) -> dict:
        repo = ProductGenomeRepository()
        try:
            rows = repo.list_genomes(limit=limit)
            return cls.response(payload={"count": len(rows), "genomes": [cls._genome_to_dict(row) for row in rows]})
        finally:
            repo.close()

    @classmethod
    def get_genome(cls, master_product_id: str) -> dict:
        repo = ProductGenomeRepository()
        try:
            row = repo.get_genome(master_product_id)
            if not row:
                return cls.response(status="NOT_FOUND", payload={"master_product_id": master_product_id})
            return cls.response(payload={"genome": cls._genome_to_dict(row)})
        finally:
            repo.close()

    @classmethod
    def summary(cls) -> dict:
        repo = ProductGenomeRepository()
        try:
            rows = repo.list_genomes(limit=1000)
            if not rows:
                return cls.response(payload={"count": 0, "business_health": 0, "message": "No Product Genomes calculated yet."})

            business_health = round(sum(row.product_health for row in rows) / len(rows))
            archetypes = {}
            for row in rows:
                archetypes[row.archetype] = archetypes.get(row.archetype, 0) + 1

            return cls.response(
                payload={
                    "count": len(rows),
                    "business_health": business_health,
                    "archetypes": archetypes,
                    "top_products": [cls._genome_to_dict(row) for row in rows[:10]],
                }
            )
        finally:
            repo.close()

    @staticmethod
    def _genome_to_dict(row) -> dict:
        return {
            "id": row.id,
            "master_product_id": row.master_product_id,
            "brand": row.brand,
            "product_family": row.product_family,
            "primary_sku": row.primary_sku,
            "name": row.name,
            "scores": {
                "product_health": row.product_health,
                "organic_strength": row.organic_strength,
                "advertising_dependency_index": row.advertising_dependency_index,
                "profitability": row.profitability,
                "growth_momentum": row.growth_momentum,
                "confidence": row.confidence,
            },
            "strategy": {
                "lifecycle_stage": row.lifecycle_stage,
                "archetype": row.archetype,
                "objective": row.objective,
                "top_opportunity": row.top_opportunity,
                "top_risk": row.top_risk,
                "executive_recommendation": row.executive_recommendation,
            },
            "metrics": row.metrics,
            "evidence": row.evidence,
            "summary": row.summary,
            "score_version": row.score_version,
            "calculated_at": row.calculated_at.isoformat() if row.calculated_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
