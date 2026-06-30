from database import SessionLocal
from models import SearchTermDailyDetail
from business_data_context import resolve_data_context, apply_date_context, apply_marketplace_context
from ai.decisions.shared import (
    make_decision,
    safe_float,
    safe_int,
    sort_decisions,
)
from decision_risk_engine import assess_decision_risk


NEGATIVE_MIN_SPEND = 3
NEGATIVE_MIN_CLICKS = 2


def get_negative_keyword_decisions(limit=25, data_context=None, country_code=None, profile_id=None):
    db = SessionLocal()

    try:
        context = data_context or resolve_data_context(
            window="latest",
            country_code=country_code,
            profile_id=profile_id,
        )

        query = (
            db.query(SearchTermDailyDetail)
            .filter(SearchTermDailyDetail.channel == "amazon_ads")
            .filter(SearchTermDailyDetail.profile_id.isnot(None))
            .filter(SearchTermDailyDetail.country_code.isnot(None))
            .filter(SearchTermDailyDetail.spend >= NEGATIVE_MIN_SPEND)
            .filter(SearchTermDailyDetail.clicks >= NEGATIVE_MIN_CLICKS)
            .filter(SearchTermDailyDetail.sales == 0)
        )

        query = apply_date_context(query, SearchTermDailyDetail, context)
        query = apply_marketplace_context(query, SearchTermDailyDetail, context)

        rows = (
            query
            .order_by(SearchTermDailyDetail.spend.desc())
            .limit(limit)
            .all()
        )

        decisions = []

        for row in rows:
            spend = safe_float(row.spend)
            clicks = safe_int(row.clicks)

            confidence = 70
            if clicks >= 5:
                confidence += 10
            if spend >= 10:
                confidence += 10
            if spend >= 20:
                confidence += 9

            confidence = min(confidence, 99)
            estimated_impact = round(spend * 30, 2)

            payload = {
                "campaign_id": str(row.campaign_id),
                "campaign_name": row.campaign_name,
                "ad_group_id": row.ad_group_id,
                "ad_group_name": row.ad_group_name,
                "keyword_id": str(row.keyword_id) if row.keyword_id else None,
                "keyword": row.keyword,
                "match_type": row.match_type,
                "search_term": row.search_term,
                "negative_match_type": "phrase",
                "profile_id": row.profile_id,
                "country_code": row.country_code,
                "marketplace": row.marketplace,
                "currency": row.currency,
                "data_window": context,
                "spend": spend,
                "clicks": clicks,
                "sales": safe_float(row.sales),
                "orders": safe_int(row.orders),
                "acos": row.acos,
                "roas": row.roas,
            }

            risk_assessment = assess_decision_risk(
                decision="ADD_NEGATIVE_KEYWORD",
                confidence=confidence,
                estimated_monthly_impact=estimated_impact,
                payload=payload,
            )

            payload["risk_assessment"] = risk_assessment

            decisions.append(
                make_decision(
                    decision="ADD_NEGATIVE_KEYWORD",
                    priority="HIGH" if confidence >= 85 else "MEDIUM",
                    confidence=confidence,
                    risk=risk_assessment["overall_risk"],
                    estimated_monthly_impact=estimated_impact,
                    reasoning=[
                        f"Data window: {context.get('start_date')} to {context.get('end_date')}.",
                        f'Search term "{row.search_term}" spent ${spend:.2f}.',
                        f"It generated {clicks} clicks and no attributed sales.",
                        "Negative keyword action is reversible and does not increase spend.",
                        f"Risk assessment: {risk_assessment['overall_risk']}.",
                    ],
                    recommended_action=f"Add negative phrase: {row.search_term}",
                    payload=payload,
                )
            )

        return {
            "status": "OK",
            "decision_type": "ADD_NEGATIVE_KEYWORD",
            "data_context": context,
            "count": len(decisions),
            "decisions": sort_decisions(decisions),
        }

    finally:
        db.close()
