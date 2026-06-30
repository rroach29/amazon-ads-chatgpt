"""
Business OS v6.2
Evidence Engine

Creates structured evidence blocks for optimizer opportunities. Reasoning text
is still returned for ChatGPT readability, but evidence gives the platform a
machine-readable basis for future learning and auditability.
"""


def _safe_float(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class EvidenceEngine:
    @staticmethod
    def search_term(row, context=None):
        spend = _safe_float(getattr(row, "spend", 0))
        sales = _safe_float(getattr(row, "sales", 0))
        clicks = _safe_int(getattr(row, "clicks", 0))
        orders = _safe_int(getattr(row, "orders", 0))
        acos = spend / sales if sales else None
        roas = sales / spend if spend else 0

        return {
            "type": "SEARCH_TERM_PERFORMANCE",
            "source": "SearchTermDailyDetail",
            "data_window": context or {},
            "campaign_id": str(getattr(row, "campaign_id", "") or ""),
            "campaign_name": getattr(row, "campaign_name", None),
            "ad_group_id": getattr(row, "ad_group_id", None),
            "ad_group_name": getattr(row, "ad_group_name", None),
            "keyword_id": str(getattr(row, "keyword_id", "") or ""),
            "keyword": getattr(row, "keyword", None),
            "match_type": getattr(row, "match_type", None),
            "search_term": getattr(row, "search_term", None),
            "profile_id": getattr(row, "profile_id", None),
            "country_code": getattr(row, "country_code", None),
            "marketplace": getattr(row, "marketplace", None),
            "currency": getattr(row, "currency", None),
            "metrics": {
                "spend": spend,
                "clicks": clicks,
                "sales": sales,
                "orders": orders,
                "acos": round(acos, 4) if acos is not None else None,
                "roas": round(roas, 4),
            },
        }

    @staticmethod
    def summarize(evidence):
        if not evidence:
            return []

        metric_block = evidence.get("metrics", {})
        search_term = evidence.get("search_term")
        spend = metric_block.get("spend", 0)
        clicks = metric_block.get("clicks", 0)
        sales = metric_block.get("sales", 0)
        orders = metric_block.get("orders", 0)
        acos = metric_block.get("acos")
        roas = metric_block.get("roas")

        lines = [
            f'Search term "{search_term}" spent ${spend:.2f}.',
            f"It generated {clicks} clicks, {orders} orders, and ${sales:.2f} sales.",
        ]

        if acos is not None:
            lines.append(f"Observed ACOS was {acos * 100:.1f}% and ROAS was {roas:.2f}.")
        else:
            lines.append("Observed ACOS is unavailable because attributed sales were $0.")

        return lines
