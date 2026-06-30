from fastapi import APIRouter, Header

from auth import verify_key
from business_data_context import resolve_data_context, explain_data_context

router = APIRouter()


@router.get("/data-context")
def data_context(
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)

    context = resolve_data_context(
        window=window,
        country_code=country_code,
        profile_id=profile_id,
        start_date=start_date,
        end_date=end_date,
    )

    return explain_data_context(context)
