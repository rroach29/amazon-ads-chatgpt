from database import SessionLocal
from models import DailyDashboard, CampaignDailyDetail, SearchTermDailyDetail


def pct_change(current, previous):
    if previous in [None, 0]:
        return None
    return round(((current - previous) / previous) * 100, 2)


def trend_direction(change):
    if change is None:
        return "UNKNOWN"
    if change > 5:
        return "UP"
    if change < -5:
        return "DOWN"
    return "FLAT"


def build_metric_trend(name, current, previous):
    change = pct_change(current or 0, previous or 0)

    return {
        "metric": name,
        "current": current or 0,
        "previous": previous or 0,
        "change_percent": change,
        "direction": trend_direction(change),
    }


def get_dashboard_rows(db, days=14):
    return (
        db.query(DailyDashboard)
        .filter(DailyDashboard.channel == "amazon_ads")
        .order_by(DailyDashboard.date.desc())
        .limit(days)
        .all()
    )


def get_account_trends(db, days=14):
    rows = list(reversed(get_dashboard_rows(db, days)))

    if len(rows) < 2:
        return {
            "status": "INSUFFICIENT_DATA",
            "message": "Need at least 2 dashboard days to calculate trends.",
            "days_available": len(rows),
        }

    midpoint = len(rows) // 2
    previous_period = rows[:midpoint]
    current_period = rows[midpoint:]

    def total(metric, period):
        return sum((getattr(row, metric) or 0) for row in period)

    def avg(metric, period):
        if not period:
            return 0
        return round(total(metric, period) / len(period), 2)

    current_spend = total("spend", current_period)
    previous_spend = total("spend", previous_period)

    current_sales = total("sales", current_period)
    previous_sales = total("sales", previous_period)

    current_orders = total("orders", current_period)
    previous_orders = total("orders", previous_period)

    current_clicks = total("clicks", current_period)
    previous_clicks = total("clicks", previous_period)

    current_impressions = total("impressions", current_period)
    previous_impressions = total("impressions", previous_period)

    current_acos = avg("acos", current_period)
    previous_acos = avg("acos", previous_period)

    current_roas = avg("roas", current_period)
    previous_roas = avg("roas", previous_period)

    return {
        "status": "OK",
        "days": days,
        "previous_period_days": len(previous_period),
        "current_period_days": len(current_period),
        "metrics": {
            "spend": build_metric_trend("spend", current_spend, previous_spend),
            "sales": build_metric_trend("sales", current_sales, previous_sales),
            "orders": build_metric_trend("orders", current_orders, previous_orders),
            "clicks": build_metric_trend("clicks", current_clicks, previous_clicks),
            "impressions": build_metric_trend(
                "impressions",
                current_impressions,
                previous_impressions,
            ),
            "acos": build_metric_trend("acos", current_acos, previous_acos),
            "roas": build_metric_trend("roas", current_roas, previous_roas),
        },
    }


def get_campaign_trends(db, days=14, limit=10):
    rows = (
        db.query(CampaignDailyDetail)
        .filter(CampaignDailyDetail.channel == "amazon_ads")
        .order_by(CampaignDailyDetail.date.desc())
        .limit(1000)
        .all()
    )

    if not rows:
        return {
            "status": "NO_DATA",
            "campaigns_improving": [],
            "campaigns_declining": [],
        }

    dates = sorted({row.date for row in rows}, reverse=True)[:days]

    if len(dates) < 2:
        return {
            "status": "INSUFFICIENT_DATA",
            "campaigns_improving": [],
            "campaigns_declining": [],
        }

    midpoint = len(dates) // 2
    current_dates = set(dates[:midpoint])
    previous_dates = set(dates[midpoint:])

    campaigns = {}

    for row in rows:
        if row.date not in current_dates and row.date not in previous_dates:
            continue

        key = row.campaign_id or row.campaign_name

        if key not in campaigns:
            campaigns[key] = {
                "campaign_id": row.campaign_id,
                "campaign_name": row.campaign_name,
                "current_sales": 0,
                "previous_sales": 0,
                "current_spend": 0,
                "previous_spend": 0,
                "current_orders": 0,
                "previous_orders": 0,
            }

        bucket = "current" if row.date in current_dates else "previous"

        campaigns[key][f"{bucket}_sales"] += row.sales or 0
        campaigns[key][f"{bucket}_spend"] += row.spend or 0
        campaigns[key][f"{bucket}_orders"] += row.orders or 0

    results = []

    for item in campaigns.values():
        sales_change = pct_change(item["current_sales"], item["previous_sales"])
        spend_change = pct_change(item["current_spend"], item["previous_spend"])

        current_acos = (
            round((item["current_spend"] / item["current_sales"]) * 100, 2)
            if item["current_sales"]
            else None
        )

        previous_acos = (
            round((item["previous_spend"] / item["previous_sales"]) * 100, 2)
            if item["previous_sales"]
            else None
        )

        acos_change = (
            pct_change(current_acos, previous_acos)
            if current_acos is not None and previous_acos is not None
            else None
        )

        score = 0

        if sales_change and sales_change > 10:
            score += 2
        if acos_change and acos_change < -10:
            score += 2
        if item["current_orders"] > item["previous_orders"]:
            score += 1

        if sales_change and sales_change < -10:
            score -= 2
        if acos_change and acos_change > 10:
            score -= 2
        if item["current_orders"] < item["previous_orders"]:
            score -= 1

        results.append({
            **item,
            "sales_change_percent": sales_change,
            "spend_change_percent": spend_change,
            "current_acos": current_acos,
            "previous_acos": previous_acos,
            "acos_change_percent": acos_change,
            "trend_score": score,
        })

    improving = sorted(results, key=lambda x: x["trend_score"], reverse=True)[:limit]
    declining = sorted(results, key=lambda x: x["trend_score"])[:limit]

    return {
        "status": "OK",
        "campaigns_improving": improving,
        "campaigns_declining": declining,
    }


def get_search_term_trends(db, days=14, limit=10):
    rows = (
        db.query(SearchTermDailyDetail)
        .filter(SearchTermDailyDetail.channel == "amazon_ads")
        .order_by(SearchTermDailyDetail.date.desc())
        .limit(2000)
        .all()
    )

    if not rows:
        return {
            "status": "NO_DATA",
            "search_terms_gaining": [],
            "search_terms_declining": [],
        }

    dates = sorted({row.date for row in rows}, reverse=True)[:days]

    if len(dates) < 2:
        return {
            "status": "INSUFFICIENT_DATA",
            "search_terms_gaining": [],
            "search_terms_declining": [],
        }

    midpoint = len(dates) // 2
    current_dates = set(dates[:midpoint])
    previous_dates = set(dates[midpoint:])

    terms = {}

    for row in rows:
        if row.date not in current_dates and row.date not in previous_dates:
            continue

        key = row.search_term

        if not key:
            continue

        if key not in terms:
            terms[key] = {
                "search_term": row.search_term,
                "campaign_name": row.campaign_name,
                "current_sales": 0,
                "previous_sales": 0,
                "current_spend": 0,
                "previous_spend": 0,
                "current_orders": 0,
                "previous_orders": 0,
                "current_clicks": 0,
                "previous_clicks": 0,
            }

        bucket = "current" if row.date in current_dates else "previous"

        terms[key][f"{bucket}_sales"] += row.sales or 0
        terms[key][f"{bucket}_spend"] += row.spend or 0
        terms[key][f"{bucket}_orders"] += row.orders or 0
        terms[key][f"{bucket}_clicks"] += row.clicks or 0

    results = []

    for item in terms.values():
        sales_change = pct_change(item["current_sales"], item["previous_sales"])
        spend_change = pct_change(item["current_spend"], item["previous_spend"])

        current_acos = (
            round((item["current_spend"] / item["current_sales"]) * 100, 2)
            if item["current_sales"]
            else None
        )

        previous_acos = (
            round((item["previous_spend"] / item["previous_sales"]) * 100, 2)
            if item["previous_sales"]
            else None
        )

        acos_change = (
            pct_change(current_acos, previous_acos)
            if current_acos is not None and previous_acos is not None
            else None
        )

        score = 0

        if sales_change and sales_change > 10:
            score += 2
        if item["current_orders"] > item["previous_orders"]:
            score += 2
        if acos_change and acos_change < -10:
            score += 1

        if spend_change and spend_change > 20 and item["current_orders"] == 0:
            score -= 3
        if acos_change and acos_change > 20:
            score -= 2
        if item["current_orders"] < item["previous_orders"]:
            score -= 1

        results.append({
            **item,
            "sales_change_percent": sales_change,
            "spend_change_percent": spend_change,
            "current_acos": current_acos,
            "previous_acos": previous_acos,
            "acos_change_percent": acos_change,
            "trend_score": score,
        })

    gaining = sorted(results, key=lambda x: x["trend_score"], reverse=True)[:limit]
    declining = sorted(results, key=lambda x: x["trend_score"])[:limit]

    return {
        "status": "OK",
        "search_terms_gaining": gaining,
        "search_terms_declining": declining,
    }


def build_trend_summary(days=14):
    db = SessionLocal()

    try:
        account = get_account_trends(db, days)
        campaigns = get_campaign_trends(db, days, limit=10)
        search_terms = get_search_term_trends(db, days, limit=10)

        return {
            "status": "OK",
            "days": days,
            "account_trends": account,
            "campaign_trends": campaigns,
            "search_term_trends": search_terms,
        }

    finally:
        db.close()
