"""Business OS v8.3 — Decision Provenance Routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from optimizers.optimizer_registry import list_optimizers, run_all_optimizers

router = APIRouter()


@router.get("/provenance/optimizers")
def business_os_optimizer_provenance(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return list_optimizers()


@router.get("/provenance/decisions")
def business_os_decision_provenance(
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    result = run_all_optimizers(window=window, country_code=country_code, profile_id=profile_id)
    decisions = result.get("decisions", [])
    missing = [
        item for item in decisions
        if item.get("optimizer_name") in (None, "", "unknown")
        or not item.get("provenance")
    ]
    return {
        "status": "OK" if not missing else "WARN",
        "schema_version": "8.3",
        "decision_count": len(decisions),
        "missing_provenance_count": len(missing),
        "decisions": decisions,
        "narrative": "Every generated decision should include optimizer identity, version, source opportunity, and provenance metadata.",
    }
