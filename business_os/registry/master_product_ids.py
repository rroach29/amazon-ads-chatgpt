"""Master Product ID generation.

Master Product IDs should be marketplace-neutral. Source information belongs in
metadata/raw fields, not in the canonical ID.
"""

from __future__ import annotations

import re

from sqlalchemy import text


class MasterProductIdService:
    version = "business-os-1.0.2-sequence-master-product-ids"
    pattern = re.compile(r"^MP-(\d{6})$")
    sequence_name = "master_product_id_seq"

    @classmethod
    def next_id(cls, db) -> str:
        """Return the next marketplace-neutral Master Product ID.

        Uses a PostgreSQL sequence so bulk imports cannot reuse the same ID inside
        one transaction. The sequence is created and advanced to at least the
        current max MP-000000 value before nextval is called.
        """
        cls.ensure_sequence(db)
        value = db.execute(text(f"SELECT nextval('{cls.sequence_name}')")).scalar()
        return f"MP-{int(value):06d}"

    @classmethod
    def ensure_sequence(cls, db) -> None:
        db.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {cls.sequence_name} START WITH 1 INCREMENT BY 1"))
        max_existing = db.execute(text("""
            SELECT COALESCE(MAX(CAST(SUBSTRING(master_product_id FROM 4) AS INTEGER)), 0)
            FROM master_products
            WHERE master_product_id ~ '^MP-[0-9]{6}$'
        """)).scalar() or 0
        db.execute(text(f"SELECT setval('{cls.sequence_name}', GREATEST((SELECT last_value FROM {cls.sequence_name}), :max_existing), true)"), {"max_existing": int(max_existing)})

    @classmethod
    def is_legacy_source_encoded_id(cls, master_product_id: str | None) -> bool:
        return bool(master_product_id and master_product_id.startswith("MP-AMZ-"))
