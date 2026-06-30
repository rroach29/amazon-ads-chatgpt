"""
Business OS v3.4.2b
Campaign Identity Resolver

Purpose:
- Prevent live Amazon Ads execution against the wrong profile.
- Resolve campaign_id to profile_id/country_code/marketplace/currency from stored dashboard campaign rows.
- Reject live execution if campaign identity cannot be resolved.

This is a safety layer between DecisionHistory and Amazon live mutation.
"""

from database import SessionLocal
from models import CampaignDailyDetail


def _normalize_campaign_id(value):
    if value is None:
        return None
    return str(value).strip()


def _normalize_country_code(value):
    return str(value).upper().strip() if value else None


def resolve_campaign_identity(campaign_id, country_code=None, profile_id=None):
    campaign_id = _normalize_campaign_id(campaign_id)
    country_code = _normalize_country_code(country_code)
    profile_id = str(profile_id).strip() if profile_id else None

    if not campaign_id:
        return {
            "status": "ERROR",
            "message": "campaign_id is required.",
            "campaign_id": campaign_id,
        }

    db = SessionLocal()

    try:
        query = (
            db.query(CampaignDailyDetail)
            .filter(CampaignDailyDetail.campaign_id == campaign_id)
        )

        if profile_id:
            query = query.filter(CampaignDailyDetail.profile_id == profile_id)

        if country_code:
            query = query.filter(CampaignDailyDetail.country_code == country_code)

        rows = (
            query
            .order_by(CampaignDailyDetail.date.desc(), CampaignDailyDetail.created_at.desc())
            .limit(10)
            .all()
        )

        if not rows:
            return {
                "status": "NO_MATCH",
                "message": "Campaign was not found in marketplace-aware dashboard storage.",
                "campaign_id": campaign_id,
                "country_code": country_code,
                "profile_id": profile_id,
            }

        # Prefer rows with complete marketplace identity.
        complete_rows = [
            row for row in rows
            if row.profile_id and row.country_code and row.marketplace
        ]

        selected = complete_rows[0] if complete_rows else rows[0]

        # Detect ambiguity. Multiple profiles for same campaign_id would be unsafe.
        profile_keys = {
            (row.profile_id, row.country_code, row.marketplace)
            for row in rows
            if row.profile_id or row.country_code or row.marketplace
        }

        if len(profile_keys) > 1 and not profile_id and not country_code:
            return {
                "status": "AMBIGUOUS",
                "message": "Campaign ID matched multiple marketplace/profile combinations. Provide country_code or profile_id before live execution.",
                "campaign_id": campaign_id,
                "matches": [
                    {
                        "profile_id": row.profile_id,
                        "country_code": row.country_code,
                        "marketplace": row.marketplace,
                        "currency": row.currency,
                        "campaign_name": row.campaign_name,
                        "date": str(row.date),
                    }
                    for row in rows
                ],
            }

        return {
            "status": "OK",
            "campaign_id": campaign_id,
            "campaign_name": selected.campaign_name,
            "campaign_status": selected.campaign_status,
            "profile_id": selected.profile_id,
            "country_code": selected.country_code,
            "marketplace": selected.marketplace,
            "currency": selected.currency,
            "date": str(selected.date),
        }

    finally:
        db.close()


def enrich_payload_with_campaign_identity(payload, existing_context=None):
    payload = payload if isinstance(payload, dict) else {}
    existing_context = existing_context if isinstance(existing_context, dict) else {}

    campaign_id = (
        payload.get("campaign_id")
        or payload.get("campaignId")
    )

    country_code = (
        payload.get("country_code")
        or payload.get("marketplace_country_code")
        or payload.get("country")
        or existing_context.get("country_code")
    )

    profile_id = (
        payload.get("profile_id")
        or existing_context.get("profile_id")
    )

    identity = resolve_campaign_identity(
        campaign_id=campaign_id,
        country_code=country_code,
        profile_id=profile_id,
    )

    if identity.get("status") != "OK":
        return {
            "status": identity.get("status"),
            "message": identity.get("message"),
            "identity": identity,
            "payload": payload,
            "context": existing_context,
        }

    enriched_payload = dict(payload)
    enriched_payload["campaign_id"] = str(identity.get("campaign_id"))
    enriched_payload["campaign_name"] = enriched_payload.get("campaign_name") or identity.get("campaign_name")
    enriched_payload["profile_id"] = enriched_payload.get("profile_id") or identity.get("profile_id")
    enriched_payload["country_code"] = enriched_payload.get("country_code") or identity.get("country_code")
    enriched_payload["marketplace"] = enriched_payload.get("marketplace") or identity.get("marketplace")
    enriched_payload["currency"] = enriched_payload.get("currency") or identity.get("currency")

    enriched_context = dict(existing_context)
    enriched_context["profile_id"] = enriched_context.get("profile_id") or identity.get("profile_id")
    enriched_context["country_code"] = enriched_context.get("country_code") or identity.get("country_code")
    enriched_context["marketplace"] = enriched_context.get("marketplace") or identity.get("marketplace")
    enriched_context["currency"] = enriched_context.get("currency") or identity.get("currency")

    return {
        "status": "OK",
        "identity": identity,
        "payload": enriched_payload,
        "context": enriched_context,
    }
