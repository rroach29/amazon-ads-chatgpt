"""Executive Brain v2.0 — Product Genome repository."""

from __future__ import annotations

from sqlalchemy import text

from business_os.platform.repositories.base import BaseRepository
from business_os.executive.genome.models import ProductGenome
from business_registry.models import MasterProduct, ProductChannel


class ProductGenomeRepository(BaseRepository):
    def master_products(self, limit: int = 500):
        return (
            self.db.query(MasterProduct)
            .order_by(MasterProduct.master_product_id.asc())
            .limit(max(1, min(limit, 5000)))
            .all()
        )

    def channels_for(self, master_product_id: str):
        return (
            self.db.query(ProductChannel)
            .filter(ProductChannel.master_product_id == master_product_id)
            .order_by(ProductChannel.channel.asc())
            .all()
        )

    def seller_central_metrics(self, master_product_id: str) -> dict:
        if not self._has_column("seller_central_sales_traffic", "master_product_id"):
            return {"available": False, "reason": "master_product_id column not found"}

        row = self.db.execute(
            text(
                """
                SELECT
                    COUNT(*) AS rows,
                    COALESCE(SUM(ordered_product_sales), 0) AS revenue,
                    COALESCE(SUM(total_order_items), 0) AS orders,
                    COALESCE(SUM(units_ordered), 0) AS units,
                    COALESCE(SUM(sessions), 0) AS sessions,
                    COALESCE(SUM(page_views), 0) AS page_views,
                    MAX(date) AS latest_date
                FROM seller_central_sales_traffic
                WHERE master_product_id = :mpid
                """
            ),
            {"mpid": master_product_id},
        ).mappings().first()

        return dict(row or {})

    def campaign_metrics(self, master_product_id: str) -> dict:
        if not self._has_column("campaign_daily_details", "master_product_id"):
            return {"available": False, "reason": "master_product_id column not found"}

        row = self.db.execute(
            text(
                """
                SELECT
                    COUNT(*) AS rows,
                    COALESCE(SUM(spend), 0) AS ad_spend,
                    COALESCE(SUM(sales), 0) AS attributed_sales_7d,
                    COALESCE(SUM(orders), 0) AS attributed_orders_7d,
                    COALESCE(SUM(clicks), 0) AS clicks,
                    COALESCE(SUM(impressions), 0) AS impressions,
                    MAX(date) AS latest_date
                FROM campaign_daily_details
                WHERE master_product_id = :mpid
                """
            ),
            {"mpid": master_product_id},
        ).mappings().first()

        return dict(row or {})

    def save_genome(self, genome_data: dict) -> ProductGenome:
        existing = (
            self.db.query(ProductGenome)
            .filter(ProductGenome.master_product_id == genome_data["master_product_id"])
            .first()
        )

        if existing:
            for key, value in genome_data.items():
                setattr(existing, key, value)
            genome = existing
        else:
            genome = ProductGenome(**genome_data)
            self.db.add(genome)

        self.db.commit()
        self.db.refresh(genome)
        return genome

    def list_genomes(self, limit: int = 250):
        return (
            self.db.query(ProductGenome)
            .order_by(ProductGenome.product_health.desc(), ProductGenome.master_product_id.asc())
            .limit(max(1, min(limit, 1000)))
            .all()
        )

    def get_genome(self, master_product_id: str):
        return (
            self.db.query(ProductGenome)
            .filter(ProductGenome.master_product_id == master_product_id)
            .first()
        )

    def _has_column(self, table: str, column: str) -> bool:
        result = self.db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_name = :table AND column_name = :column
                """
            ),
            {"table": table, "column": column},
        ).scalar()
        return bool(result)
