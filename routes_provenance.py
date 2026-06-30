"""Business OS v8.4.1 — Optimizer Manifest and Decision Provenance Routes.

This router intentionally exposes both the v8.3 provenance paths and the
simpler regression-suite path used by Swagger testing.
"""

from fastapi import APIRouter, Header

from auth import verify_key
from optimizers.optimizer_registry import list_optimizers, run_all_optimizers

router = APIRouter()


@router.get("/optimizer-manifests")
def business_os_optimizer_manifests(x_api_key: str = Header(...)):
    """Return registered optimizer manifests for platform diagnostics and planners."""
    verify_key(x_api_key)
    return list_optimizers()


@router.get("/provenance/optimizers")
def business_os_optimizer_provenance(x_api_key: str = Header(...)):
    """Backward-compatible v8.3 optimizer provenance endpoint."""
    verify_key(x_api_key)
    return list_optimizers()


@router.get("/provenance/decisions")
def business_os_decision_provenance(
    window: str = "latest",
    country_code: str | None = None,
    profile_id: str | None = None,
    x_api_key: str = Header(...),
):
    """Inspect generated decisions for optimizer provenance metadata."""
    verify_key(x_api_key)
    result = run_all_optimizers(window=window, country_code=country_code, profile_id=profile_id)
    decisions = result.get("decisions", [])
    missing = [
        item
        for item in decisions
        if item.get("optimizer_name") in (None, "", "unknown") or not item.get("provenance")
    ]
    return {
        "status": "OK" if not missing else "WARN",
        "schema_version": "8.4.1",
        "decision_count": len(decisions),
        "missing_provenance_count": len(missing),
        "decisions": decisions,
        "narrative": "Every generated decision should include optimizer identity, version, source opportunity, and provenance metadata.",
    }
