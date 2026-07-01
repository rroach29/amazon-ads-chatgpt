"""Business Registry v1.3 — Registry Manager API routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from business_os.registry.manager.schemas import (
    ChannelMappingCreate,
    ChannelMappingUpdate,
    MasterProductCreate,
    MasterProductUpdate,
)
from business_os.registry.manager.service import RegistryManagerService

router = APIRouter()


@router.get("/registry-manager/products")
def registry_manager_find_products(
    q: str | None = None,
    status: str | None = None,
    active: bool | None = None,
    limit: int = 100,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RegistryManagerService.find_products(q=q, status=status, active=active, limit=limit)


@router.post("/registry-manager/products")
def registry_manager_create_product(
    payload: MasterProductCreate,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RegistryManagerService.create_master_product(payload)


@router.put("/registry-manager/products/{master_product_id}")
def registry_manager_update_product(
    master_product_id: str,
    payload: MasterProductUpdate,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RegistryManagerService.update_master_product(master_product_id, payload)


@router.post("/registry-manager/products/{master_product_id}/archive")
def registry_manager_archive_product(
    master_product_id: str,
    reason: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RegistryManagerService.archive_master_product(master_product_id, reason=reason)


@router.get("/registry-manager/mapping-completeness")
def registry_manager_mapping_completeness(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return RegistryManagerService.mapping_completeness()


@router.post("/registry-manager/channel-mappings")
def registry_manager_create_channel_mapping(
    payload: ChannelMappingCreate,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RegistryManagerService.create_channel_mapping(payload)


@router.put("/registry-manager/channel-mappings/{mapping_id}")
def registry_manager_update_channel_mapping(
    mapping_id: int,
    payload: ChannelMappingUpdate,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RegistryManagerService.update_channel_mapping(mapping_id, payload)


@router.delete("/registry-manager/channel-mappings/{mapping_id}")
def registry_manager_delete_channel_mapping(
    mapping_id: int,
    hard_delete: bool = False,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return RegistryManagerService.delete_channel_mapping(mapping_id, hard_delete=hard_delete)
