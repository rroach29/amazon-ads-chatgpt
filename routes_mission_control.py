from fastapi import APIRouter, Header

from auth import verify_key
from mission_control import get_mission_control

router = APIRouter()


@router.get("/mission-control")
def mission_control(
    objective: str | None = None,
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)

    return get_mission_control(
        objective=objective,
        window=window,
        country_code=country_code,
        profile_id=profile_id,
    )
