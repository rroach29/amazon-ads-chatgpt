from fastapi import APIRouter, Header

from auth import verify_key
from optimizers.optimizer_registry import (
    list_optimizers,
    run_optimizer,
    run_all_optimizers,
)

router = APIRouter()


@router.get("/optimizers")
def optimizers(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return list_optimizers()


@router.get("/optimizers/run")
def run_optimizers(
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)

    return run_all_optimizers(
        window=window,
        country_code=country_code,
        profile_id=profile_id,
    )


@router.get("/optimizers/{optimizer_name}/run")
def run_single_optimizer(
    optimizer_name: str,
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)

    from business_data_context import resolve_data_context

    context = resolve_data_context(
        window=window,
        country_code=country_code,
        profile_id=profile_id,
    )

    return run_optimizer(optimizer_name, context=context)
