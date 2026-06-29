from datetime import date

from database import SessionLocal
from models import DailyDashboard, CampaignDailyDetail, SearchTermDailyDetail
from amazon_ads import download_report_data
from analytics import build_dashboard_analysis
from marketplace_profiles import get_marketplace_profile


def _normalize_country_code(country_code):
    return str(country_code).upper() if country_code else None


def _resolve_marketplace_context(
    profile_id=None,
    country_code=None,
    marketplace=None,
    currency=None,
):
    context = {
        "profile_id": str(profile_id) if profile_id else None,
        "country_code": _normalize_country_code(country_code),
        "marketplace": marketplace,
        "currency": currency,
    }

    if context["country_code"] and (
        not context["profile_id"]
        or not context["marketplace"]
        or not context["currency"]
    ):
        try:
            profile_response = get_marketplace_profile(context["country_code"])
            if profile_response.get("status") == "OK":
                profile = profile_response.get("profile", {})
                context["profile_id"] = context["profile_id"] or str(profile.get("profile_id") or "")
                context["marketplace"] = context["marketplace"] or profile.get("marketplace")
                context["currency"] = context["currency"] or profile.get("currency")
        except Exception:
            pass

    return context


def save_dashboard_from_reports(
    campaign_report_id: str,
    search_term_report_id: str,
    profile_id: str | None = None,
    country_code: str | None = None,
    marketplace: str | None = None,
    currency: str | None = None,
):
    context = _resolve_marketplace_context(
        profile_id=profile_id,
        country_code=country_code,
        marketplace=marketplace,
        currency=currency,
    )

    campaign_download = download_report_data(
        campaign_report_id,
        country_code=context["country_code"],
        profile_id=context["profile_id"],
    )
    search_download = download_report_data(
        search_term_report_id,
        country_code=context["country_code"],
        profile_id=context["profile_id"],
    )

    if not campaign_download.get("ready") or not search_download.get("ready"):
        return {
            "status": "PENDING",
            "message": "One or both reports are not ready yet.",
            "campaignStatus": campaign_download.get("status"),
            "searchTermStatus": search_download.get("status"),
            "marketplace_context": context,
        }

    analysis = build_dashboard_analysis(
        campaign_download.get("data", []),
        search_download.get("data", []),
    )

    campaigns = analysis["campaigns"]
    search_terms = analysis["search_terms"]
    summary = analysis["summary"]
    today = date.today()

    db = SessionLocal()

    try:
        campaign_delete_query = db.query(CampaignDailyDetail).filter(
            CampaignDailyDetail.date == today,
            CampaignDailyDetail.channel == "amazon_ads",
        )

        search_delete_query = db.query(SearchTermDailyDetail).filter(
            SearchTermDailyDetail.date == today,
            SearchTermDailyDetail.channel == "amazon_ads",
        )

        if context["profile_id"]:
            campaign_delete_query = campaign_delete_query.filter(
                CampaignDailyDetail.profile_id == context["profile_id"]
            )
            search_delete_query = search_delete_query.filter(
                SearchTermDailyDetail.profile_id == context["profile_id"]
            )
        elif context["country_code"]:
            campaign_delete_query = campaign_delete_query.filter(
                CampaignDailyDetail.country_code == context["country_code"]
            )
            search_delete_query = search_delete_query.filter(
                SearchTermDailyDetail.country_code == context["country_code"]
            )

        campaign_delete_query.delete()
        search_delete_query.delete()

        for r in campaigns:
            db.add(
                CampaignDailyDetail(
                    date=today,
                    channel="amazon_ads",
                    profile_id=context["profile_id"],
                    country_code=context["country_code"],
                    marketplace=context["marketplace"],
                    currency=context["currency"],
                    campaign_id=str(r.get("campaignId") or ""),
                    campaign_name=r.get("campaignName"),
                    campaign_status=r.get("campaignStatus"),
                    impressions=r.get("impressions", 0),
                    clicks=r.get("clicks", 0),
                    spend=r.get("spend", 0),
                    sales=r.get("sales", 0),
                    orders=r.get("orders", 0),
                    acos=r.get("acos"),
                    roas=r.get("roas"),
                    ctr=r.get("ctr"),
                    cpc=r.get("cpc"),
                    conversion_rate=r.get("conversionRate"),
                    raw=r,
                )
            )

        for r in search_terms:
            db.add(
                SearchTermDailyDetail(
                    date=today,
                    channel="amazon_ads",
                    profile_id=context["profile_id"],
                    country_code=context["country_code"],
                    marketplace=context["marketplace"],
                    currency=context["currency"],
                    campaign_id=str(r.get("campaignId") or ""),
                    campaign_name=r.get("campaignName"),
                    ad_group_id=str(r.get("adGroupId") or ""),
                    ad_group_name=r.get("adGroupName"),
                    keyword_id=str(r.get("keywordId") or ""),
                    keyword=r.get("keyword"),
                    match_type=r.get("matchType"),
                    search_term=r.get("searchTerm"),
                    impressions=r.get("impressions", 0),
                    clicks=r.get("clicks", 0),
                    spend=r.get("spend", 0),
                    sales=r.get("sales", 0),
                    orders=r.get("orders", 0),
                    acos=r.get("acos"),
                    roas=r.get("roas"),
                    ctr=r.get("ctr"),
                    cpc=r.get("cpc"),
                    conversion_rate=r.get("conversionRate"),
                    raw=r,
                )
            )

        existing_query = (
            db.query(DailyDashboard)
            .filter(DailyDashboard.date == today)
            .filter(DailyDashboard.channel == "amazon_ads")
        )

        if context["profile_id"]:
            existing_query = existing_query.filter(DailyDashboard.profile_id == context["profile_id"])
        elif context["country_code"]:
            existing_query = existing_query.filter(DailyDashboard.country_code == context["country_code"])

        existing = existing_query.first()

        if existing:
            existing.profile_id = context["profile_id"]
            existing.country_code = context["country_code"]
            existing.marketplace = context["marketplace"]
            existing.currency = context["currency"]
            existing.spend = summary["spend"]
            existing.sales = summary["sales"]
            existing.acos = summary["acos"]
            existing.roas = summary["roas"]
            existing.clicks = summary["clicks"]
            existing.impressions = summary["impressions"]
            existing.orders = summary["orders"]
            existing.health_score = analysis["health_score"]
            existing.alerts = analysis["alerts"]
            existing.recommendations = analysis["recommendations"]
        else:
            db.add(
                DailyDashboard(
                    date=today,
                    channel="amazon_ads",
                    profile_id=context["profile_id"],
                    country_code=context["country_code"],
                    marketplace=context["marketplace"],
                    currency=context["currency"],
                    spend=summary["spend"],
                    sales=summary["sales"],
                    acos=summary["acos"],
                    roas=summary["roas"],
                    clicks=summary["clicks"],
                    impressions=summary["impressions"],
                    orders=summary["orders"],
                    health_score=analysis["health_score"],
                    alerts=analysis["alerts"],
                    recommendations=analysis["recommendations"],
                )
            )

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    return {
        "status": "OK",
        "message": "Dashboard collected and saved.",
        "marketplace_context": context,
        "summary": summary,
        "health_score": analysis["health_score"],
        "alerts": analysis["alerts"],
        "recommendations": analysis["recommendations"],
    }


def get_latest_dashboard(country_code: str | None = None, profile_id: str | None = None):
    db = SessionLocal()

    try:
        query = db.query(DailyDashboard).filter(DailyDashboard.channel == "amazon_ads")

        if profile_id:
            query = query.filter(DailyDashboard.profile_id == str(profile_id))
        elif country_code:
            query = query.filter(DailyDashboard.country_code == _normalize_country_code(country_code))

        latest = query.order_by(DailyDashboard.date.desc()).first()

        if not latest:
            return {
                "status": "NO_DATA",
                "message": "Database is connected, but no dashboard data has been collected yet.",
                "country_code": _normalize_country_code(country_code),
                "profile_id": str(profile_id) if profile_id else None,
            }

        return {
            "status": "OK",
            "date": str(latest.date),
            "channel": latest.channel,
            "profile_id": latest.profile_id,
            "country_code": latest.country_code,
            "marketplace": latest.marketplace,
            "currency": latest.currency,
            "summary": {
                "spend": latest.spend,
                "sales": latest.sales,
                "acos": latest.acos,
                "roas": latest.roas,
                "clicks": latest.clicks,
                "impressions": latest.impressions,
                "orders": latest.orders,
                "health_score": latest.health_score,
            },
            "alerts": latest.alerts,
            "recommendations": latest.recommendations,
        }

    finally:
        db.close()


def get_dashboard_history(days: int = 30, country_code: str | None = None, profile_id: str | None = None):
    db = SessionLocal()

    try:
        query = db.query(DailyDashboard).filter(DailyDashboard.channel == "amazon_ads")

        if profile_id:
            query = query.filter(DailyDashboard.profile_id == str(profile_id))
        elif country_code:
            query = query.filter(DailyDashboard.country_code == _normalize_country_code(country_code))

        rows = query.order_by(DailyDashboard.date.desc()).limit(days).all()
        rows = list(reversed(rows))

        return {
            "status": "OK",
            "days": days,
            "country_code": _normalize_country_code(country_code),
            "profile_id": str(profile_id) if profile_id else None,
            "history": [
                {
                    "date": str(row.date),
                    "profile_id": row.profile_id,
                    "country_code": row.country_code,
                    "marketplace": row.marketplace,
                    "currency": row.currency,
                    "spend": row.spend,
                    "sales": row.sales,
                    "acos": row.acos,
                    "roas": row.roas,
                    "clicks": row.clicks,
                    "impressions": row.impressions,
                    "orders": row.orders,
                    "health_score": row.health_score,
                }
                for row in rows
            ],
        }

    finally:
        db.close()


def serialize_campaign(row):
    return {
        "date": str(row.date),
        "channel": row.channel,
        "profile_id": row.profile_id,
        "country_code": row.country_code,
        "marketplace": row.marketplace,
        "currency": row.currency,
        "campaign_id": row.campaign_id,
        "campaign_name": row.campaign_name,
        "campaign_status": row.campaign_status,
        "impressions": row.impressions,
        "clicks": row.clicks,
        "spend": row.spend,
        "sales": row.sales,
        "orders": row.orders,
        "acos": row.acos,
        "roas": row.roas,
        "ctr": row.ctr,
        "cpc": row.cpc,
        "conversion_rate": row.conversion_rate,
    }


def serialize_search_term(row):
    return {
        "date": str(row.date),
        "channel": row.channel,
        "profile_id": row.profile_id,
        "country_code": row.country_code,
        "marketplace": row.marketplace,
        "currency": row.currency,
        "campaign_id": row.campaign_id,
        "campaign_name": row.campaign_name,
        "ad_group_id": row.ad_group_id,
        "ad_group_name": row.ad_group_name,
        "keyword_id": row.keyword_id,
        "keyword": row.keyword,
        "match_type": row.match_type,
        "search_term": row.search_term,
        "impressions": row.impressions,
        "clicks": row.clicks,
        "spend": row.spend,
        "sales": row.sales,
        "orders": row.orders,
        "acos": row.acos,
        "roas": row.roas,
        "ctr": row.ctr,
        "cpc": row.cpc,
        "conversion_rate": row.conversion_rate,
    }


def _apply_marketplace_filters(query, model, country_code=None, profile_id=None):
    if profile_id:
        return query.filter(model.profile_id == str(profile_id))
    if country_code:
        return query.filter(model.country_code == _normalize_country_code(country_code))
    return query


def get_campaigns(limit: int = 100, country_code: str | None = None, profile_id: str | None = None):
    db = SessionLocal()

    try:
        query = db.query(CampaignDailyDetail).filter(CampaignDailyDetail.channel == "amazon_ads")
        query = _apply_marketplace_filters(query, CampaignDailyDetail, country_code, profile_id)

        rows = query.order_by(CampaignDailyDetail.date.desc(), CampaignDailyDetail.spend.desc()).limit(limit).all()

        return {
            "status": "OK",
            "count": len(rows),
            "country_code": _normalize_country_code(country_code),
            "profile_id": str(profile_id) if profile_id else None,
            "campaigns": [serialize_campaign(row) for row in rows],
        }

    finally:
        db.close()


def get_top_campaigns(limit: int = 25, country_code: str | None = None, profile_id: str | None = None):
    db = SessionLocal()

    try:
        query = (
            db.query(CampaignDailyDetail)
            .filter(CampaignDailyDetail.channel == "amazon_ads")
            .filter(CampaignDailyDetail.sales > 0)
        )
        query = _apply_marketplace_filters(query, CampaignDailyDetail, country_code, profile_id)

        rows = query.order_by(CampaignDailyDetail.sales.desc()).limit(limit).all()

        return {
            "status": "OK",
            "count": len(rows),
            "country_code": _normalize_country_code(country_code),
            "profile_id": str(profile_id) if profile_id else None,
            "campaigns": [serialize_campaign(row) for row in rows],
        }

    finally:
        db.close()


def get_waste_campaigns(min_spend: float = 10, limit: int = 25, country_code: str | None = None, profile_id: str | None = None):
    db = SessionLocal()

    try:
        query = (
            db.query(CampaignDailyDetail)
            .filter(CampaignDailyDetail.channel == "amazon_ads")
            .filter(CampaignDailyDetail.spend >= min_spend)
            .filter(CampaignDailyDetail.sales == 0)
        )
        query = _apply_marketplace_filters(query, CampaignDailyDetail, country_code, profile_id)

        rows = query.order_by(CampaignDailyDetail.spend.desc()).limit(limit).all()

        return {
            "status": "OK",
            "min_spend": min_spend,
            "count": len(rows),
            "country_code": _normalize_country_code(country_code),
            "profile_id": str(profile_id) if profile_id else None,
            "campaigns": [serialize_campaign(row) for row in rows],
        }

    finally:
        db.close()


def get_search_terms(limit: int = 100, country_code: str | None = None, profile_id: str | None = None):
    db = SessionLocal()

    try:
        query = db.query(SearchTermDailyDetail).filter(SearchTermDailyDetail.channel == "amazon_ads")
        query = _apply_marketplace_filters(query, SearchTermDailyDetail, country_code, profile_id)

        rows = query.order_by(SearchTermDailyDetail.date.desc(), SearchTermDailyDetail.spend.desc()).limit(limit).all()

        return {
            "status": "OK",
            "count": len(rows),
            "country_code": _normalize_country_code(country_code),
            "profile_id": str(profile_id) if profile_id else None,
            "search_terms": [serialize_search_term(row) for row in rows],
        }

    finally:
        db.close()


def get_winning_search_terms(max_acos: float = 35, min_orders: int = 1, limit: int = 25, country_code: str | None = None, profile_id: str | None = None):
    db = SessionLocal()

    try:
        query = (
            db.query(SearchTermDailyDetail)
            .filter(SearchTermDailyDetail.channel == "amazon_ads")
            .filter(SearchTermDailyDetail.orders >= min_orders)
            .filter(SearchTermDailyDetail.acos <= max_acos)
        )
        query = _apply_marketplace_filters(query, SearchTermDailyDetail, country_code, profile_id)

        rows = query.order_by(SearchTermDailyDetail.sales.desc()).limit(limit).all()

        return {
            "status": "OK",
            "max_acos": max_acos,
            "min_orders": min_orders,
            "count": len(rows),
            "country_code": _normalize_country_code(country_code),
            "profile_id": str(profile_id) if profile_id else None,
            "search_terms": [serialize_search_term(row) for row in rows],
        }

    finally:
        db.close()


def get_wasted_search_terms(min_spend: float = 10, limit: int = 25, country_code: str | None = None, profile_id: str | None = None):
    db = SessionLocal()

    try:
        query = (
            db.query(SearchTermDailyDetail)
            .filter(SearchTermDailyDetail.channel == "amazon_ads")
            .filter(SearchTermDailyDetail.spend >= min_spend)
            .filter(SearchTermDailyDetail.sales == 0)
        )
        query = _apply_marketplace_filters(query, SearchTermDailyDetail, country_code, profile_id)

        rows = query.order_by(SearchTermDailyDetail.spend.desc()).limit(limit).all()

        return {
            "status": "OK",
            "min_spend": min_spend,
            "count": len(rows),
            "country_code": _normalize_country_code(country_code),
            "profile_id": str(profile_id) if profile_id else None,
            "search_terms": [serialize_search_term(row) for row in rows],
        }

    finally:
        db.close()
