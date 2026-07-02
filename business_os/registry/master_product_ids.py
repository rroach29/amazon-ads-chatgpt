"""Master Product ID generation.

Master Product IDs should be marketplace-neutral. Source information belongs in
metadata/raw fields, not in the canonical ID.
"""

from __future__ import annotations

import re

from business_registry.models import MasterProduct


class MasterProductIdService:
    version = "business-os-1.0.0-sequential-master-product-ids"
    pattern = re.compile(r"^MP-(\d{6})$")

    @classmethod
    def next_id(cls, db) -> str:
        max_number = 0
        rows = db.query(MasterProduct.master_product_id).filter(MasterProduct.master_product_id.like("MP-%")).all()
        for (value,) in rows:
            match = cls.pattern.match(value or "")
            if match:
                max_number = max(max_number, int(match.group(1)))
        candidate = max_number + 1
        while True:
            master_product_id = f"MP-{candidate:06d}"
            exists = db.query(MasterProduct).filter(MasterProduct.master_product_id == master_product_id).first()
            if not exists:
                return master_product_id
            candidate += 1

    @classmethod
    def is_legacy_source_encoded_id(cls, master_product_id: str | None) -> bool:
        return bool(master_product_id and master_product_id.startswith("MP-AMZ-"))
