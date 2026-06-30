"""Business OS v8.2 — Domain Model Routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from domain import DomainRegistry

router = APIRouter()


@router.get("/domain/models")
def business_os_domain_models(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return DomainRegistry.list_models()


@router.get("/domain/schema")
def business_os_domain_schema(
    model_name: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return DomainRegistry.schema(model_name=model_name)


@router.get("/domain/sample")
def business_os_domain_sample(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return DomainRegistry.sample()
