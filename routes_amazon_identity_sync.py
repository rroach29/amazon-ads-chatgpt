"""Amazon Product Identity Sync routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from business_os.registry.amazon_identity_sync import AmazonIdentitySyncService
from business_os.registry.amazon_listings_discovery import AmazonListingsDiscoveryService
from business_os.registry.manual_identity_link import ManualIdentityLinkService
from business_os.registry.master_product_admin import MasterProductAdminService
from business_os.registry.registry_integrity import RegistryIntegrityService
from business_os.registry.registry_merge import RegistryMergeService

router = APIRouter()


@router.get("/registry/integrity/audit")
def registry_integrity_audit(limit: int = 100, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return RegistryIntegrityService.audit(limit=limit)


@router.post("/registry/master-product/title")
def registry_master_product_title_update(master_product_id: str, title: str, approve: bool = False, reason: str | None = None, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return MasterProductAdminService.update_title(master_product_id=master_product_id, title=title, approve=approve, reason=reason)


@router.post("/registry/master-product/update")
def registry_master_product_update(
    master_product_id: str,
    name: str | None = None,
    brand: str | None = None,
    product_family: str | None = None,
    primary_sku: str | None = None,
    status: str | None = None,
    lifecycle_stage: str | None = None,
    approve: bool = False,
    reason: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return MasterProductAdminService.update_fields(
        master_product_id=master_product_id,
        name=name,
        brand=brand,
        product_family=product_family,
        primary_sku=primary_sku,
        status=status,
        lifecycle_stage=lifecycle_stage,
        approve=approve,
        reason=reason,
    )


@router.get("/registry/integrity/merge-preview")
def registry_merge_preview(keeper_master_product_id: str, duplicate_master_product_id: str, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return RegistryMergeService.preview(keeper_master_product_id=keeper_master_product_id, duplicate_master_product_id=duplicate_master_product_id)


@router.post("/registry/integrity/merge")
def registry_merge(keeper_master_product_id: str, duplicate_master_product_id: str, approve: bool = False, allow_variation_family: bool = False, reason: str | None = None, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return RegistryMergeService.merge(keeper_master_product_id=keeper_master_product_id, duplicate_master_product_id=duplicate_master_product_id, approve=approve, allow_variation_family=allow_variation_family, reason=reason)


@router.get("/registry/identity-link/preview")
def registry_identity_link_preview(master_product_id: str, channel: str = "Amazon", marketplace: str | None = None, asin: str | None = None, sku: str | None = None, title: str | None = None, status: str | None = None, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return ManualIdentityLinkService.preview(master_product_id=master_product_id, channel=channel, marketplace=marketplace, asin=asin, sku=sku, title=title, status=status)


@router.post("/registry/identity-link")
def registry_identity_link(master_product_id: str, channel: str = "Amazon", marketplace: str | None = None, asin: str | None = None, sku: str | None = None, title: str | None = None, status: str | None = None, approve: bool = False, reason: str | None = None, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return ManualIdentityLinkService.link(master_product_id=master_product_id, channel=channel, marketplace=marketplace, asin=asin, sku=sku, title=title, status=status, approve=approve, reason=reason)


@router.get("/registry/amazon-identity/summary")
def amazon_identity_summary(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return AmazonIdentitySyncService.summary()


@router.get("/registry/amazon-identity/seller-central-diagnostics")
def amazon_seller_central_identity_diagnostics(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return AmazonIdentitySyncService.seller_central_diagnostics()


@router.get("/registry/amazon-listings/preview")
def amazon_listings_preview(marketplace: str = "US", page_size: int = 20, page_token: str | None = None, included_data: str = "summaries,attributes,offers,fulfillmentAvailability,issues", x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return AmazonListingsDiscoveryService.preview(marketplace=marketplace, page_size=page_size, page_token=page_token, included_data=included_data)


@router.post("/registry/amazon-listings/sync")
def amazon_listings_sync(marketplace: str = "US", dry_run: bool = True, page_size: int = 20, page_token: str | None = None, included_data: str = "summaries,attributes,offers,fulfillmentAvailability,issues", create_missing_products: bool = False, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return AmazonListingsDiscoveryService.sync(marketplace=marketplace, dry_run=dry_run, page_size=page_size, page_token=page_token, included_data=included_data, create_missing_products=create_missing_products)


@router.post("/registry/amazon-listings/sync-all")
def amazon_listings_sync_all(marketplace: str = "US", dry_run: bool = True, page_size: int = 20, max_pages: int = 10, included_data: str = "summaries,attributes,offers,fulfillmentAvailability,issues", create_missing_products: bool = False, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return AmazonListingsDiscoveryService.sync_all(marketplace=marketplace, dry_run=dry_run, page_size=page_size, max_pages=max_pages, included_data=included_data, create_missing_products=create_missing_products)


@router.post("/registry/amazon-identity/sync")
def amazon_identity_sync(dry_run: bool = True, limit: int = 1000, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return AmazonIdentitySyncService.sync_from_seller_central(dry_run=dry_run, limit=limit)
