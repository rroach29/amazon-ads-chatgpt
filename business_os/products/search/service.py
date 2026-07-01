from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import inspect, text

from database import SessionLocal, engine
from business_registry.models import BusinessEvent, MasterProduct


class ProductSearchIntelligenceService:
    version = "business-os-0.4.1"
    SEARCH_TABLE = "search_term_daily_details"

    @classmethod
    def summary(cls, limit: int = 250) -> dict[str, Any]:
        db = SessionLocal()
        try:
            products = db.query(MasterProduct).filter(MasterProduct.active == True).limit(max(1, min(limit, 500))).all()
            items = []
            for product in products:
                data = cls._build_for_product(db, product.master_product_id)
                if data.get("has_search_data"):
                    items.append(data)
            items.sort(key=lambda x: (-(x.get("wasted_spend_30d") or 0), x.get("search_health") or 999))
            return {"status": "OK", "version": cls.version, "count": len(items), "products": items, "portfolio": cls._portfolio_summary(items)}
        finally:
            db.close()

    @classmethod
    def product_search(cls, master_product_id: str) -> dict[str, Any]:
        db = SessionLocal()
        try:
            product = db.query(MasterProduct).filter(MasterProduct.master_product_id == master_product_id).first()
            if not product:
                return {"status": "NOT_FOUND", "version": cls.version, "master_product_id": master_product_id}
            return {"status": "OK", "version": cls.version, "search": cls._build_for_product(db, master_product_id)}
        finally:
            db.close()

    @classmethod
    def generate_mission_control_decisions(cls, limit: int = 250, replace_existing_product_search_decisions: bool = True) -> dict[str, Any]:
        db = SessionLocal()
        try:
            from business_os.mission_control.models import MissionControlDecision
            if replace_existing_product_search_decisions:
                db.query(MissionControlDecision).filter(MissionControlDecision.source == "product_search_intelligence").filter(MissionControlDecision.status == "Pending").delete()
            summary = cls.summary(limit=limit)
            created = []
            for item in summary.get("products", []):
                for rec in item.get("recommendations", [])[:3]:
                    decision = MissionControlDecision(
                        decision_id=f"DEC-{uuid4().hex[:12].upper()}", master_product_id=item.get("master_product_id"), product_name=item.get("product_name"),
                        title=rec.get("title"), category="Search Terms", priority=rec.get("priority", "MEDIUM"), status="Pending",
                        estimated_monthly_impact=float(rec.get("estimated_monthly_impact") or 0), confidence=int(rec.get("confidence") or 70),
                        reversibility=rec.get("reversibility", "High"), urgency=int(rec.get("urgency") or 70), recommendation=rec.get("recommendation"),
                        reason=rec.get("reason"), why_now=rec.get("why_now"), if_you_do=rec.get("if_you_do"), if_you_do_not=rec.get("if_you_do_not"),
                        evidence=rec.get("evidence", []), actions=[{"id":"approve","label":"Approve"},{"id":"simulate","label":"Simulate"},{"id":"explain","label":"Explain"},{"id":"defer","label":"Defer"},{"id":"dismiss","label":"Dismiss"}],
                        source="product_search_intelligence", payload={"version": cls.version, "search_health": item.get("search_health")},
                    )
                    db.add(decision); created.append(decision)
            cls._record_event(db, "ProductSearchDecisionsGenerated", f"Generated {len(created)} Product Search Intelligence decisions.", payload={"created": len(created), "version": cls.version})
            db.commit()
            return {"status": "OK", "version": cls.version, "created_count": len(created), "portfolio": summary.get("portfolio")}
        except Exception as exc:
            db.rollback(); return {"status": "ERROR", "version": cls.version, "message": str(exc)}
        finally:
            db.close()

    @classmethod
    def _build_for_product(cls, db, master_product_id: str) -> dict[str, Any]:
        product = db.query(MasterProduct).filter(MasterProduct.master_product_id == master_product_id).first()
        if not product: return {"master_product_id": master_product_id, "has_search_data": False}
        if not cls._table_exists(cls.SEARCH_TABLE): return cls._empty_product(product, "search_term_daily_details table not found")
        if not cls._has_column(cls.SEARCH_TABLE, "master_product_id"): return cls._empty_product(product, "search_term_daily_details.master_product_id column not found")
        rows = cls._search_rows(db, master_product_id)
        if not rows: return cls._empty_product(product, "No linked search-term rows found for this Master Product")
        terms = cls._group_terms(rows); totals = cls._totals(terms)
        winning_terms = cls._winning_terms(terms); waste_terms = cls._waste_terms(terms); harvest_terms = cls._harvest_terms(terms); negative_candidates = cls._negative_candidates(terms); discovery_terms = cls._discovery_terms(terms)
        health = cls._search_health(totals, winning_terms, waste_terms, harvest_terms)
        recs = cls._recommendations(product, totals, winning_terms, waste_terms, harvest_terms, negative_candidates, health)
        return {
            "master_product_id": product.master_product_id, "product_name": product.name, "primary_sku": product.primary_sku, "brand": product.brand,
            "has_search_data": True, "search_health": health, "search_term_count": len(terms), "winning_term_count": len(winning_terms),
            "harvest_candidate_count": len(harvest_terms), "negative_candidate_count": len(negative_candidates), "waste_term_count": len(waste_terms), "discovery_term_count": len(discovery_terms),
            "spend_30d": round(totals["spend"],2), "sales_30d": round(totals["sales"],2), "wasted_spend_30d": round(sum(t.get("spend_30d",0) for t in waste_terms),2),
            "clicks_30d": int(totals["clicks"]), "impressions_30d": int(totals["impressions"]), "orders_30d": int(totals["orders"]),
            "acos": round(totals["acos"],4) if totals["acos"] is not None else None, "acos_pct": round(totals["acos"]*100,2) if totals["acos"] is not None else None,
            "roas": round(totals["roas"],2) if totals["roas"] is not None else None, "conversion_rate": round(totals["conversion_rate"],4) if totals["conversion_rate"] is not None else None,
            "conversion_rate_pct": round(totals["conversion_rate"]*100,2) if totals["conversion_rate"] is not None else None,
            "winning_terms": winning_terms[:25], "waste_terms": waste_terms[:25], "harvest_terms": harvest_terms[:25], "negative_candidates": negative_candidates[:25], "discovery_terms": discovery_terms[:25],
            "recommendations": recs, "data_note": None,
        }

    @classmethod
    def _search_rows(cls, db, master_product_id: str):
        cols = cls._columns(cls.SEARCH_TABLE); select_cols = ", ".join([f'"{c}"' for c in cols]); order_col = cls._date_order_column(cols)
        sql = f'''SELECT {select_cols} FROM "{cls.SEARCH_TABLE}" WHERE master_product_id = :mpid ORDER BY {order_col} DESC LIMIT 10000'''
        return [dict(row) for row in db.execute(text(sql), {"mpid": master_product_id}).mappings().all()]

    @classmethod
    def _group_terms(cls, rows):
        grouped = {}
        for row in rows:
            raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
            term = cls._first(row, raw, ["search_term","searchTerm","customerSearchTerm","query"]) or cls._first(row, raw, ["keyword","keywordText","targeting"]) or "Unknown Search Term"
            key = str(term).strip().lower()
            g = grouped.setdefault(key, {"search_term": str(term).strip(), "campaign_name": cls._first(row, raw, ["campaign_name","campaignName","campaign"]), "ad_group_name": cls._first(row, raw, ["ad_group_name","adGroupName"]), "match_type": cls._first(row, raw, ["match_type","matchType","keywordType"]) or "Unknown", "spend_30d":0.0, "sales_30d":0.0, "clicks_30d":0, "impressions_30d":0, "orders_30d":0, "rows":0})
            g["spend_30d"] += cls._num(cls._first(row, raw, ["spend","cost"])); g["sales_30d"] += cls._num(cls._first(row, raw, ["sales","sales7d","attributedSales7d","totalSales"])); g["clicks_30d"] += int(cls._num(cls._first(row, raw, ["clicks"]))); g["impressions_30d"] += int(cls._num(cls._first(row, raw, ["impressions"]))); g["orders_30d"] += int(cls._num(cls._first(row, raw, ["orders","purchases7d","attributedConversions7d","conversions"]))); g["rows"] += 1
        terms = []
        for g in grouped.values():
            spend, sales, clicks, impressions, orders = g["spend_30d"], g["sales_30d"], g["clicks_30d"], g["impressions_30d"], g["orders_30d"]
            g["acos"] = spend/sales if sales else None; g["acos_pct"] = round(g["acos"]*100,2) if g["acos"] is not None else None; g["roas"] = sales/spend if spend else None; g["ctr"] = clicks/impressions if impressions else None; g["ctr_pct"] = round(g["ctr"]*100,2) if g["ctr"] is not None else None; g["cpc"] = spend/clicks if clicks else None; g["conversion_rate"] = orders/clicks if clicks else None; g["conversion_rate_pct"] = round(g["conversion_rate"]*100,2) if g["conversion_rate"] is not None else None
            terms.append(g)
        terms.sort(key=lambda x: x.get("spend_30d",0), reverse=True); return terms

    @staticmethod
    def _totals(terms):
        spend=sum(t.get("spend_30d",0) or 0 for t in terms); sales=sum(t.get("sales_30d",0) or 0 for t in terms); clicks=sum(t.get("clicks_30d",0) or 0 for t in terms); impressions=sum(t.get("impressions_30d",0) or 0 for t in terms); orders=sum(t.get("orders_30d",0) or 0 for t in terms)
        return {"spend":spend,"sales":sales,"clicks":clicks,"impressions":impressions,"orders":orders,"acos":spend/sales if sales else None,"roas":sales/spend if spend else None,"conversion_rate":orders/clicks if clicks else None}
    @staticmethod
    def _winning_terms(terms): return sorted([t for t in terms if t.get("orders_30d",0)>=2 and t.get("sales_30d",0)>=40 and (t.get("acos") is None or t.get("acos")<=0.35)], key=lambda t:(t.get("orders_30d",0),t.get("sales_30d",0)), reverse=True)
    @staticmethod
    def _waste_terms(terms): return sorted([t for t in terms if t.get("spend_30d",0)>=15 and t.get("sales_30d",0)==0 and t.get("orders_30d",0)==0], key=lambda t:t.get("spend_30d",0), reverse=True)
    @staticmethod
    def _harvest_terms(terms): return sorted([t for t in terms if t.get("orders_30d",0)>=2 and t.get("sales_30d",0)>=50 and str(t.get("match_type","")).lower() not in ["exact","exact match"] and (t.get("acos") is None or t.get("acos")<=0.40)], key=lambda t:(t.get("orders_30d",0),t.get("sales_30d",0)), reverse=True)
    @staticmethod
    def _negative_candidates(terms): return sorted([t for t in terms if t.get("clicks_30d",0)>=15 and t.get("orders_30d",0)==0 and t.get("spend_30d",0)>=10], key=lambda t:(t.get("spend_30d",0),t.get("clicks_30d",0)), reverse=True)
    @staticmethod
    def _discovery_terms(terms): return sorted([t for t in terms if (1 <= t.get("orders_30d",0) < 2) or (t.get("clicks_30d",0)>=5 and t.get("sales_30d",0)>0)], key=lambda t:t.get("sales_30d",0), reverse=True)

    @staticmethod
    def _search_health(totals, winners, waste, harvest):
        score=70; spend=totals.get("spend",0) or 0; wasted=sum(t.get("spend_30d",0) for t in waste); ratio=wasted/spend if spend else 0
        if winners: score += min(18, len(winners)*3)
        if harvest: score += min(10, len(harvest)*2)
        if ratio >= .35: score -= 30
        elif ratio >= .20: score -= 18
        elif ratio >= .10: score -= 8
        if totals.get("acos") is not None:
            if totals["acos"] <= .30: score += 8
            elif totals["acos"] >= .70: score -= 18
        return max(0, min(100, int(score)))

    @classmethod
    def _recommendations(cls, product, totals, winning_terms, waste_terms, harvest_terms, negative_candidates, health):
        recs=[]; name=product.name or product.master_product_id
        if harvest_terms:
            t=harvest_terms[0]; recs.append(cls._rec(f"Harvest winning search term for {name}", "HIGH", max(40, t.get("sales_30d",0)*.12), 88, 90, f"Create or verify Exact Match coverage for '{t.get('search_term')}'.", "This search term has sales and orders at efficient ACOS but is not currently Exact Match.", "Promoting proven customer search terms helps capture more profitable traffic and improves control.", "You may increase profitable sales and gain cleaner bid control for this product.", "The term may remain buried in broader match traffic with less control.", [{"signal":"search_term","value":t.get("search_term")},{"signal":"orders_30d","value":t.get("orders_30d")},{"signal":"sales_30d","value":round(t.get("sales_30d",0),2)},{"signal":"acos_pct","value":t.get("acos_pct")},{"signal":"match_type","value":t.get("match_type")}]))
        if negative_candidates:
            t=negative_candidates[0]; recs.append(cls._rec(f"Add negative keyword candidate for {name}", "HIGH", max(15, t.get("spend_30d",0)*.70), 84, 86, f"Review '{t.get('search_term')}' as a Negative Exact or Negative Phrase candidate.", "The term has clicks and spend but no orders.", "This is a direct wasted-spend signal.", "You may prevent future wasted spend from irrelevant or weak search traffic.", "The product may keep spending on a search term that has not converted.", [{"signal":"search_term","value":t.get("search_term")},{"signal":"clicks_30d","value":t.get("clicks_30d")},{"signal":"spend_30d","value":round(t.get("spend_30d",0),2)},{"signal":"orders_30d","value":t.get("orders_30d")}]))
        wasted=sum(t.get("spend_30d",0) for t in waste_terms)
        if wasted>=50: recs.append(cls._rec(f"Clean up wasted search spend for {name}", "MEDIUM", wasted*.50, 82, 78, f"Review the top {min(5,len(waste_terms))} waste terms and add negatives where appropriate.", "Multiple search terms have spend with no attributed sales.", "Waste can accumulate quietly across many low-performing terms.", "You may reduce wasted spend and improve product-level advertising efficiency.", "Small waste terms may keep draining budget across campaigns.", [{"signal":"waste_term_count","value":len(waste_terms)},{"signal":"wasted_spend_30d","value":round(wasted,2)}]))
        if not recs and winning_terms:
            t=winning_terms[0]; recs.append(cls._rec(f"Search terms are healthy for {name}", "LOW", 0, 74, 35, f"Keep monitoring winning search term '{t.get('search_term')}'.", "The product has efficient winning search terms and no urgent waste signal.", "Stable search performance should not be over-optimized without a clear reason.", "You preserve performance stability.", "No immediate downside detected.", [{"signal":"search_health","value":health}]))
        return recs[:5]

    @staticmethod
    def _rec(title, priority, impact, confidence, urgency, recommendation, reason, why_now, if_do, if_not, evidence): return {"title":title,"priority":priority,"estimated_monthly_impact":round(float(impact),2),"confidence":confidence,"reversibility":"High","urgency":urgency,"recommendation":recommendation,"reason":reason,"why_now":why_now,"if_you_do":if_do,"if_you_do_not":if_not,"evidence":evidence}
    @staticmethod
    def _portfolio_summary(items):
        if not items: return {"products_with_search_data":0,"average_search_health":None,"total_spend_30d":0,"total_sales_30d":0,"total_wasted_spend_30d":0,"portfolio_acos_pct":None,"recommendation_count":0,"harvest_candidate_count":0,"negative_candidate_count":0}
        spend=sum(i.get("spend_30d",0) or 0 for i in items); sales=sum(i.get("sales_30d",0) or 0 for i in items); wasted=sum(i.get("wasted_spend_30d",0) or 0 for i in items); health=round(sum(i.get("search_health",0) or 0 for i in items)/len(items))
        return {"products_with_search_data":len(items),"average_search_health":health,"total_spend_30d":round(spend,2),"total_sales_30d":round(sales,2),"total_wasted_spend_30d":round(wasted,2),"portfolio_acos_pct":round((spend/sales)*100,2) if sales else None,"recommendation_count":sum(len(i.get("recommendations",[])) for i in items),"harvest_candidate_count":sum(i.get("harvest_candidate_count",0) for i in items),"negative_candidate_count":sum(i.get("negative_candidate_count",0) for i in items)}
    @staticmethod
    def _empty_product(product, note): return {"master_product_id":product.master_product_id,"product_name":product.name,"primary_sku":product.primary_sku,"brand":product.brand,"has_search_data":False,"search_health":None,"search_term_count":0,"winning_term_count":0,"harvest_candidate_count":0,"negative_candidate_count":0,"waste_term_count":0,"spend_30d":0,"sales_30d":0,"wasted_spend_30d":0,"recommendations":[],"winning_terms":[],"waste_terms":[],"harvest_terms":[],"negative_candidates":[],"discovery_terms":[],"data_note":note}
    @staticmethod
    def _first(row, raw, names):
        for name in names:
            if name in row and row.get(name) is not None: return row.get(name)
            if isinstance(raw, dict) and name in raw and raw.get(name) is not None: return raw.get(name)
        raw_lower={str(k).lower():v for k,v in raw.items()} if isinstance(raw,dict) else {}; row_lower={str(k).lower():v for k,v in row.items()}
        for name in names:
            key=name.lower()
            if row_lower.get(key) is not None: return row_lower.get(key)
            if raw_lower.get(key) is not None: return raw_lower.get(key)
        return None
    @staticmethod
    def _num(value):
        if value is None: return 0.0
        try: return float(value.replace("$","").replace(",","").replace("%","").strip()) if isinstance(value,str) else float(value)
        except Exception: return 0.0
    @staticmethod
    def _date_order_column(cols):
        for candidate in ["date","report_date","startDate","created_at","id"]:
            if candidate in cols: return f'"{candidate}"'
        return '"id"'
    @staticmethod
    def _table_exists(table): return inspect(engine).has_table(table)
    @staticmethod
    def _columns(table): return [c["name"] for c in inspect(engine).get_columns(table)]
    @classmethod
    def _has_column(cls, table, column): return column in cls._columns(table)
    @staticmethod
    def _record_event(db, event_type, title, master_product_id=None, payload=None): db.add(BusinessEvent(event_id=f"EV-{uuid4().hex[:12].upper()}", event_type=event_type, occurred_at=datetime.utcnow(), master_product_id=master_product_id, title=title, source="product_search_intelligence", payload=payload or {}))
