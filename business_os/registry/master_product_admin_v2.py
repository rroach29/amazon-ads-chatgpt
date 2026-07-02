"""Sequential-ID wrapper for Master Product admin.

Keeps the existing admin service behavior, but replaces UUID-style Master Product
creation with marketplace-neutral sequential IDs.
"""

from __future__ import annotations

from business_os.registry.master_product_admin import MasterProductAdminService as _BaseMasterProductAdminService
from business_os.registry.master_product_ids import MasterProductIdService


class MasterProductAdminService(_BaseMasterProductAdminService):
    version = "business-os-1.0.1-sequential-master-product-ids"

    @staticmethod
    def _next_master_product_id(db) -> str:
        return MasterProductIdService.next_id(db)
