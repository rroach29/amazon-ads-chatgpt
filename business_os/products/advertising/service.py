"""Business OS v0.4.0 — Product Advertising Intelligence.

Product-first advertising intelligence. Campaigns are evidence; Master Products are the decision object.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import inspect, text

from database import SessionLocal, engine
from business_registry.models import BusinessEvent, MasterProduct


class ProductAdvertisingIntelligenceService:
    version = "business-os-0.4.0"
    CAMPAIGN_TABLE = "campaign_daily_details"

    @classmethod
    def summary(cls, limit: int = 100) -> dict[str, Any]:
        db = SessionLocal()
        try:
            products = db.query(MasterProduct).filter(MasterProduct.active == True).limit(max(1, min(limit, 500))).all()
            items = []
            for product in products:
                intelligence = cls._build_for_product(db, product.master_product_id)
                if intelligence.get("has_ad_data"):
                    items.append(intelligence)
            items.sort(key=lambda x: (x.get("advertising_health", 999), -x.get("spend_30d", 0)))
            return {"status": "OK", "version": cls.version, "count": len(items), "products": items, "portfolio": cls._portfolio_summary(items)}
        finally:
            db.close()

    @classmethod
    def product_advertising(cls, master_product_id: str) -> dict[str, Any]:
        db = SessionLocal()
        try:
            product = db.query(MasterProduct).filter(MasterProduct.master_product_id == master_product_id).first()
            if not product:
                return {"status": "NOT_FOUND", "version": cls.version, "master_product_id": master_product_id}
            return {"status": "OK", "version": cls.version, "advertising": cls._build_for_product(db, master_product_id)}
        finally:
            db.close()

    @classmethod
    def generate_mission_control_decisions(cls, limit: int = 250, replace_existing_product_ad_decisions: bool = True) -> dict[str, Any]:
        db = SessionLocal()
        try:
            from business_os.mission_control.models import MissionControlDecision
            if replace_existing_product_ad_decisions:
                db.query(MissionControlDecision).filter(MissionControlDecision.source == "product_advertising_intelligence").filter(MissionControlDecision.status == "Pending").delete()
            summary = cls.summary(limit=limit)
            created = []
            for item in summary.get("products", []):
                for rec in item.get("recommendations", [])[:2]:
                    decision = MissionControlDecision(
                        decision_id=f"DEC-{uuid4().hex[:12].upper()}",
                        master_product_id=item.get("master_product_id"),
                        product_name=item.get("product_name"),
                        title=rec.get("title") or f"Review advertising for {item.get('product_name')}",
                        category="Advertising",
                        priority=rec.get("priority", "MEDIUM"),
                        status="Pending",
                        estimated_monthly_impact=float(rec.get("estimated_monthly_impact") or 0),
                        confidence=int(rec.get("confidence") or 70),
                        reversibility=rec.get("reversibility", "High"),
                        urgency=int(rec.get("urgency") or 70),
                        recommendation=rec.get("recommendation"),
                        reason=rec.get("reason"),
                        why_now=rec.get("why_now"),
                        if_you_do=rec.get("if_you_do"),
                        if_you_do_not=rec.get("if_you_do_not"),
                        evidence=rec.get("evidence", []),
                        actions=[
                            {"id": "approve", "label": "Approve"}, {"id": "simulate", "label": "Simulate"},
                            {"id": "explain", "label": "Explain"}, {"id": "defer", "label": "Defer"},
                            {"id": "dismiss", "label": "Dismiss"},
                        ],
                        source="product_advertising_intelligence",
                        payload={"version": cls.version, "health": item.get("advertising_health")},
                    )
                    db.add(decision); created.append(decision)
            cls._record_event(db, "ProductAdvertisingDecisionsGenerated", f"Generated {len(created)} Product Advertising Intelligence decisions.", payload={"created": len(created), "version": cls.version})
            db.commit()
            return {"status": "OK", "version": cls.version, "created_count": len(created), "portfolio": summary.get("portfolio")}
        except Exception as exc:
            db.rollback(); return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @classmethod
    def _build_for_product(cls, db, master_product_id: str) -> dict[str, Any]:
        product = db.query(MasterProduct).filter(MasterProduct.master_product_id == master_product_id).first()
        if not product: return {"master_product_id": master_product_id, "has_ad_data": False}
        if not cls._table_exists(cls.CAMPAIGN_TABLE): return cls._empty_product(product, "campaign_daily_details table not found")
        if not cls._has_column(cls.CAMPAIGN_TABLE, "master_product_id"): return cls._empty_product(product, "campaign_daily_details.master_product_id column not found")
        rows = cls._campaign_rows(db, master_product_id)
        if not rows: return cls._empty_product(product, "No linked campaign rows found for this Master Product")
        campaigns = cls._group_campaigns(rows)
        totals = cls._totals(campaigns)
        health = cls._health_score(totals, campaigns)
        trend = cls._trend(totals)
        recs = cls._recommendations(product, totals, campaigns, health, trend)
        sorted_by_sales = sorted(campaigns, key=lambda r: r.get("sales_30d", 0), reverse=True)
        sorted_by_waste = sorted(campaigns, key=lambda r: ((r.get("acos") or 0), r.get("spend_30d", 0)), reverse=True)
        return {
            "master_product_id": product.master_product_id, "product_name": product.name, "primary_sku": product.primary_sku, "brand": product.brand,
            "has_ad_data": True, "advertising_health": health, "trend": trend, "campaign_count": len(campaigns),
            "active_campaigns": len([c for c in campaigns if str(c.get("status", "")).lower() == "enabled"]),
            "paused_campaigns": len([c for c in campaigns if str(c.get("status", "")).lower() == "paused"]),
            "spend_30d": round(totals["spend"], 2), "sales_30d": round(totals["sales"], 2),
            "clicks_30d": int(totals["clicks"]), "impressions_30d": int(totals["impressions"]), "orders_30d": int(totals["orders"]),
            "acos": round(totals["acos"], 4) if totals["acos"] is not None else None,
            "acos_pct": round(totals["acos"] * 100, 2) if totals["acos"] is not None else None,
            "roas": round(totals["roas"], 2) if totals["roas"] is not None else None,
            "ctr": round(totals["ctr"], 4) if totals["ctr"] is not None else None,
            "ctr_pct": round(totals["ctr"] * 100, 2) if totals["ctr"] is not None else None,
            "cpc": round(totals["cpc"], 2) if totals["cpc"] is not None else None,
            "conversion_rate": round(totals["conversion_rate"], 4) if totals["conversion_rate"] is not None else None,
            "conversion_rate_pct": round(totals["conversion_rate"] * 100, 2) if totals["conversion_rate"] is not None else None,
            "top_campaign": sorted_by_sales[0] if sorted_by_sales else None,
            "worst_campaign": sorted_by_waste[0] if sorted_by_waste else None,
            "campaigns": campaigns, "recommendations": recs, "data_note": None,
        }

    @classmethod
    def _campaign_rows(cls, db, master_product_id: str) -> list[dict[str, Any]]:
        cols = cls._columns(cls.CAMPAIGN_TABLE)
        select_cols = ", ".join([f'"{c}"' for c in cols])
        sql = f'SELECT {select_cols} FROM "{cls.CAMPAIGN_TABLE}" WHERE master_product_id = :mpid ORDER BY {cls._date_order_column(cols)} DESC LIMIT 5000'
        return [dict(row) for row in db.execute(text(sql), {"mpid": master_product_id}).mappings().all()]

    @classmethod
    def _group_campaigns(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped = {}
        for row in rows:
            raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
            campaign_id = cls._first(row, raw, ["campaign_id", "campaignId"])
            campaign_name = cls._first(row, raw, ["campaign_name", "campaignName", "campaign"])
            key = str(campaign_id or campaign_name or row.get("id"))
            g = grouped.setdefault(key, {"campaign_id": campaign_id, "campaign_name": campaign_name or "Unknown Campaign", "status": cls._first(row, raw, ["campaign_status", "campaignStatus", "status"]) or "Unknown", "spend_30d": 0.0, "sales_30d": 0.0, "clicks_30d": 0, "impressions_30d": 0, "orders_30d": 0, "rows": 0})
            g["spend_30d"] += cls._num(cls._first(row, raw, ["spend", "cost"]))
            g["sales_30d"] += cls._num(cls._first(row, raw, ["sales", "sales7d", "attributedSales7d", "totalSales"]))
            g["clicks_30d"] += int(cls._num(cls._first(row, raw, ["clicks"])))
            g["impressions_30d"] += int(cls._num(cls._first(row, raw, ["impressions"])))
            g["orders_30d"] += int(cls._num(cls._first(row, raw, ["orders", "purchases7d", "attributedConversions7d", "conversions"])))
            g["rows"] += 1
        campaigns = []
        for g in grouped.values():
            spend, sales, clicks, impressions, orders = g["spend_30d"], g["sales_30d"], g["clicks_30d"], g["impressions_30d"], g["orders_30d"]
            g["acos"] = spend / sales if sales else None
            g["acos_pct"] = round(g["acos"] * 100, 2) if g["acos"] is not None else None
            g["roas"] = sales / spend if spend else None
            g["ctr"] = clicks / impressions if impressions else None
            g["ctr_pct"] = round(g["ctr"] * 100, 2) if g["ctr"] is not None else None
            g["cpc"] = spend / clicks if clicks else None
            g["conversion_rate"] = orders / clicks if clicks else None
            g["health"] = cls._campaign_health(g)
            campaigns.append(g)
        campaigns.sort(key=lambda x: x.get("spend_30d", 0), reverse=True)
        return campaigns

    @staticmethod
    def _totals(campaigns):
        spend = sum(c.get("spend_30d", 0) or 0 for c in campaigns); sales = sum(c.get("sales_30d", 0) or 0 for c in campaigns)
        clicks = sum(c.get("clicks_30d", 0) or 0 for c in campaigns); impressions = sum(c.get("impressions_30d", 0) or 0 for c in campaigns); orders = sum(c.get("orders_30d", 0) or 0 for c in campaigns)
        return {"spend": spend, "sales": sales, "clicks": clicks, "impressions": impressions, "orders": orders, "acos": spend/sales if sales else None, "roas": sales/spend if spend else None, "ctr": clicks/impressions if impressions else None, "cpc": spend/clicks if clicks else None, "conversion_rate": orders/clicks if clicks else None}

    @staticmethod
    def _health_score(totals, campaigns) -> int:
        score = 70; acos = totals.get("acos"); roas = totals.get("roas"); conv = totals.get("conversion_rate"); ctr = totals.get("ctr")
        if acos is None and totals.get("spend", 0) > 0: score -= 35
        elif acos is not None:
            if acos <= 0.25: score += 20
            elif acos <= 0.40: score += 8
            elif acos <= 0.70: score -= 10
            else: score -= 25
        if roas is not None:
            if roas >= 4: score += 10
            elif roas < 1.5: score -= 15
        if conv is not None:
            if conv >= 0.10: score += 8
            elif conv < 0.03: score -= 10
        if ctr is not None:
            if ctr >= 0.004: score += 5
            elif ctr < 0.001: score -= 5
        waste = [c for c in campaigns if (c.get("spend_30d", 0) >= 25 and not c.get("sales_30d"))]
        score -= min(20, len(waste) * 5)
        return max(0, min(100, int(score)))

    @staticmethod
    def _campaign_health(campaign) -> int:
        score = 70; spend = campaign.get("spend_30d", 0) or 0; sales = campaign.get("sales_30d", 0) or 0; acos = campaign.get("acos"); conv = campaign.get("conversion_rate")
        if spend >= 25 and sales == 0: score -= 45
        elif acos is not None:
            if acos <= 0.25: score += 20
            elif acos <= 0.40: score += 8
            elif acos <= 0.70: score -= 12
            else: score -= 30
        if conv is not None:
            if conv >= 0.10: score += 8
            elif conv < 0.03: score -= 8
        return max(0, min(100, int(score)))

    @staticmethod
    def _trend(totals) -> str:
        spend = totals.get("spend", 0) or 0; sales = totals.get("sales", 0) or 0; acos = totals.get("acos")
        if spend == 0: return "No Advertising Data"
        if sales == 0: return "Needs Attention"
        if acos is not None and acos <= 0.30: return "Healthy"
        if acos is not None and acos <= 0.50: return "Watch"
        return "Needs Attention"

    @classmethod
    def _recommendations(cls, product, totals, campaigns, health, trend):
        recs = []; spend = totals.get("spend", 0) or 0; sales = totals.get("sales", 0) or 0; product_name = product.name or product.master_product_id
        waste = [c for c in campaigns if (c.get("spend_30d", 0) >= 25 and not c.get("sales_30d"))]
        waste.sort(key=lambda c: c.get("spend_30d", 0), reverse=True)
        if waste:
            c = waste[0]; impact = max(25, c.get("spend_30d", 0) * 0.35)
            recs.append({"title": f"Investigate wasted spend for {product_name}", "priority": "HIGH", "estimated_monthly_impact": round(impact,2), "confidence": 88, "reversibility": "High", "urgency": 92, "recommendation": f"Review campaign '{c.get('campaign_name')}' because it has spend but no attributed sales.", "reason": "A linked campaign has advertising spend with zero attributed sales.", "why_now": "This is a direct cash leak unless the campaign is intentionally gathering launch data.", "if_you_do": "You may reduce wasted ad spend while preserving budget for stronger campaigns.", "if_you_do_not": "The product may continue spending on traffic that is not converting.", "evidence": [{"signal":"campaign","value":c.get('campaign_name')},{"signal":"spend_30d","value":round(c.get('spend_30d',0),2)},{"signal":"sales_30d","value":round(c.get('sales_30d',0),2)},{"signal":"clicks_30d","value":c.get('clicks_30d',0)}]})
        high_acos = [c for c in campaigns if c.get("acos") is not None and c.get("acos") >= 0.60 and c.get("spend_30d", 0) >= 25]
        high_acos.sort(key=lambda c: (c.get("acos", 0), c.get("spend_30d", 0)), reverse=True)
        if high_acos:
            c = high_acos[0]; impact = max(30, c.get("spend_30d", 0) * 0.20)
            recs.append({"title": f"Reduce advertising pressure on {product_name}", "priority": "HIGH" if c.get("acos",0) >= .80 else "MEDIUM", "estimated_monthly_impact": round(impact,2), "confidence": 82, "reversibility": "High", "urgency": 84, "recommendation": f"Consider reducing bids or isolating poor targets in '{c.get('campaign_name')}'.", "reason": "The campaign has high ACOS and enough spend to matter.", "why_now": "High ACOS can quietly reduce product profitability even when sales look healthy.", "if_you_do": "Profit may improve if the campaign is trimmed without materially reducing sales.", "if_you_do_not": "Advertising may continue subsidizing low-profit or unprofitable sales.", "evidence": [{"signal":"campaign","value":c.get('campaign_name')},{"signal":"acos_pct","value":c.get('acos_pct')},{"signal":"spend_30d","value":round(c.get('spend_30d',0),2)},{"signal":"sales_30d","value":round(c.get('sales_30d',0),2)}]})
        strong = [c for c in campaigns if c.get("acos") is not None and c.get("acos") <= .25 and c.get("sales_30d",0) >= 50]
        strong.sort(key=lambda c: c.get("sales_30d",0), reverse=True)
        if strong:
            c = strong[0]
            recs.append({"title": f"Consider scaling strong advertising for {product_name}", "priority": "MEDIUM", "estimated_monthly_impact": round(max(40, c.get('sales_30d',0)*.08),2), "confidence": 78, "reversibility": "Medium", "urgency": 68, "recommendation": f"Review budget and impression share for '{c.get('campaign_name')}' before scaling.", "reason": "A linked campaign has strong sales with efficient ACOS.", "why_now": "Efficient campaigns can be underfunded, especially when budgets are conservative.", "if_you_do": "You may capture more profitable sales if the campaign has room to scale.", "if_you_do_not": "Growth may remain constrained while budget goes to weaker campaigns.", "evidence": [{"signal":"campaign","value":c.get('campaign_name')},{"signal":"acos_pct","value":c.get('acos_pct')},{"signal":"sales_30d","value":round(c.get('sales_30d',0),2)},{"signal":"roas","value":round(c.get('roas') or 0,2)}]})
        if spend > 0 and sales == 0 and not recs:
            recs.append({"title": f"Pause and diagnose advertising for {product_name}", "priority": "HIGH", "estimated_monthly_impact": round(max(25, spend*.30),2), "confidence": 86, "reversibility": "High", "urgency": 90, "recommendation": "Review all linked campaigns before continuing spend.", "reason": "This product has advertising spend but no attributed advertising sales.", "why_now": "This is one of the clearest wasted-spend signals.", "if_you_do": "You may stop unproductive spend and redirect budget to products with stronger demand.", "if_you_do_not": "Spend may continue with no measurable return.", "evidence": [{"signal":"spend_30d","value":round(spend,2)},{"signal":"sales_30d","value":round(sales,2)}]})
        if not recs and health >= 80:
            recs.append({"title": f"Advertising is healthy for {product_name}", "priority": "LOW", "estimated_monthly_impact": 0, "confidence": 75, "reversibility": "High", "urgency": 35, "recommendation": "No urgent advertising action. Continue monitoring.", "reason": "Product advertising health is strong.", "why_now": "Healthy products should not be over-optimized without a clear reason.", "if_you_do": "You preserve stability.", "if_you_do_not": "No immediate downside detected.", "evidence": [{"signal":"advertising_health","value":health}]})
        return recs[:5]

    @staticmethod
    def _portfolio_summary(items):
        if not items: return {"products_with_ad_data":0,"average_advertising_health":None,"total_spend_30d":0,"total_sales_30d":0,"portfolio_acos_pct":None,"recommendation_count":0}
        spend=sum(i.get("spend_30d",0) or 0 for i in items); sales=sum(i.get("sales_30d",0) or 0 for i in items); health=round(sum(i.get("advertising_health",0) or 0 for i in items)/len(items))
        return {"products_with_ad_data":len(items),"average_advertising_health":health,"total_spend_30d":round(spend,2),"total_sales_30d":round(sales,2),"portfolio_acos_pct":round((spend/sales)*100,2) if sales else None,"recommendation_count":sum(len(i.get("recommendations",[])) for i in items)}

    @staticmethod
    def _empty_product(product, note):
        return {"master_product_id": product.master_product_id, "product_name": product.name, "primary_sku": product.primary_sku, "brand": product.brand, "has_ad_data": False, "advertising_health": None, "trend": "No Data", "campaign_count":0, "active_campaigns":0, "paused_campaigns":0, "spend_30d":0, "sales_30d":0, "acos":None, "recommendations":[], "campaigns":[], "data_note": note}

    @staticmethod
    def _first(row, raw, names):
        for name in names:
            if name in row and row.get(name) is not None: return row.get(name)
            if name in raw and raw.get(name) is not None: return raw.get(name)
        raw_lower={str(k).lower():v for k,v in raw.items()} if isinstance(raw,dict) else {}; row_lower={str(k).lower():v for k,v in row.items()}
        for name in names:
            key=name.lower()
            if row_lower.get(key) is not None: return row_lower.get(key)
            if raw_lower.get(key) is not None: return raw_lower.get(key)
        return None

    @staticmethod
    def _num(value):
        if value is None: return 0.0
        try:
            if isinstance(value, str): return float(value.replace("$","").replace(",","").replace("%","").strip())
            return float(value)
        except Exception: return 0.0

    @staticmethod
    def _date_order_column(cols):
        for c in ["date", "report_date", "startDate", "created_at", "id"]:
            if c in cols: return f'"{c}"'
        return '"id"'

    @staticmethod
    def _table_exists(table): return inspect(engine).has_table(table)
    @staticmethod
    def _columns(table): return [c["name"] for c in inspect(engine).get_columns(table)]
    @classmethod
    def _has_column(cls, table, column): return column in cls._columns(table)
    @staticmethod
    def _record_event(db, event_type, title, master_product_id=None, payload=None):
        db.add(BusinessEvent(event_id=f"EV-{uuid4().hex[:12].upper()}", event_type=event_type, occurred_at=datetime.utcnow(), master_product_id=master_product_id, title=title, source="product_advertising_intelligence", payload=payload or {}))
