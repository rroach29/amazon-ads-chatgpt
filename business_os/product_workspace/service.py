"""Business OS v0.6.4 — Product Workspace Dashboard.

Includes:
- Product Dashboard output
- Product Metrics integration
- v0.6.2 defensive ProductGenome/ProductChannel serializers
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import desc

from database import SessionLocal
from business_registry.models import BusinessEvent, MasterProduct, ProductChannel
from business_os.executive.genome.models import ProductGenome
from business_os.execution_framework.models import ExecutionPlan, ExecutionResult
from business_os.mission_control.models import MissionControlDecision
from business_os.product_metrics.service import ProductMetricsService

try:
    from business_os.products.advertising.service import ProductAdvertisingIntelligenceService
except Exception:
    ProductAdvertisingIntelligenceService = None

try:
    from business_os.products.search.service import ProductSearchIntelligenceService
except Exception:
    ProductSearchIntelligenceService = None


class ProductWorkspaceService:
    version = "business-os-0.6.4"

    @classmethod
    def portfolio(cls, limit: int = 250, query: str | None = None) -> dict[str, Any]:
        db = SessionLocal()
        try:
            q = db.query(MasterProduct).filter(MasterProduct.active == True)
            if query:
                pattern = f"%{query}%"
                q = q.filter(
                    (MasterProduct.name.ilike(pattern))
                    | (MasterProduct.primary_sku.ilike(pattern))
                    | (MasterProduct.brand.ilike(pattern))
                    | (MasterProduct.product_family.ilike(pattern))
                )

            products = q.order_by(MasterProduct.name).limit(max(1, min(limit, 500))).all()
            items = [cls._portfolio_item(db, product) for product in products]

            items.sort(key=lambda item: (
                -(item.get("open_decisions") or 0),
                -(item.get("ad_sales_30d") or 0),
                item.get("product_name") or "",
            ))

            return {
                "status": "OK",
                "version": cls.version,
                "count": len(items),
                "summary": cls._portfolio_summary(items),
                "products": items,
            }
        finally:
            db.close()

    @classmethod
    def workspace(cls, master_product_id: str) -> dict[str, Any]:
        db = SessionLocal()
        try:
            product = db.query(MasterProduct).filter(MasterProduct.master_product_id == master_product_id).first()
            if not product:
                return {"status": "NOT_FOUND", "version": cls.version, "master_product_id": master_product_id}

            channels = db.query(ProductChannel).filter(ProductChannel.master_product_id == master_product_id).order_by(ProductChannel.channel, ProductChannel.marketplace).all()
            genome = db.query(ProductGenome).filter(ProductGenome.master_product_id == master_product_id).first()
            decisions = db.query(MissionControlDecision).filter(MissionControlDecision.master_product_id == master_product_id).order_by(desc(MissionControlDecision.created_at)).limit(50).all()
            plans = db.query(ExecutionPlan).filter(ExecutionPlan.master_product_id == master_product_id).order_by(desc(ExecutionPlan.created_at)).limit(50).all()
            results = db.query(ExecutionResult).join(ExecutionPlan, ExecutionResult.plan_id == ExecutionPlan.plan_id).filter(ExecutionPlan.master_product_id == master_product_id).order_by(desc(ExecutionResult.created_at)).limit(50).all()
            events = db.query(BusinessEvent).filter(BusinessEvent.master_product_id == master_product_id).order_by(desc(BusinessEvent.occurred_at)).limit(25).all()

            advertising = cls._advertising(master_product_id)
            search = cls._search(master_product_id)
            metrics_payload = ProductMetricsService.product_metrics(master_product_id)
            metrics = metrics_payload.get("metrics", {}) if metrics_payload.get("status") == "OK" else {}

            return {
                "status": "OK",
                "version": cls.version,
                "product": cls._product(product),
                "dashboard": cls._dashboard(product, genome, advertising, search, decisions, plans, metrics),
                "metrics": metrics_payload,
                "channels": [cls._channel(row) for row in channels],
                "genome": cls._genome(genome),
                "advertising": advertising,
                "search": search,
                "mission_control": {
                    "open_decisions": len([d for d in decisions if d.status == "Pending"]),
                    "approved_decisions": len([d for d in decisions if d.status == "Approved"]),
                    "recent_decisions": [cls._decision(row) for row in decisions],
                },
                "execution": {
                    "plans": [cls._plan(row) for row in plans],
                    "history": [cls._result(row) for row in results],
                },
                "timeline": [cls._event(row) for row in events],
                "workspace_summary": cls._workspace_summary(product, genome, advertising, search, decisions, plans, metrics),
            }
        finally:
            db.close()

    @classmethod
    def product_decisions(cls, master_product_id: str, status: str = "Pending", limit: int = 100) -> dict[str, Any]:
        db = SessionLocal()
        try:
            query = db.query(MissionControlDecision).filter(MissionControlDecision.master_product_id == master_product_id)
            if status:
                query = query.filter(MissionControlDecision.status == status)
            rows = query.order_by(desc(MissionControlDecision.created_at)).limit(max(1, min(limit, 500))).all()
            return {"status": "OK", "version": cls.version, "master_product_id": master_product_id, "count": len(rows), "decisions": [cls._decision(row) for row in rows]}
        finally:
            db.close()

    @classmethod
    def product_execution(cls, master_product_id: str, limit: int = 100) -> dict[str, Any]:
        db = SessionLocal()
        try:
            plans = db.query(ExecutionPlan).filter(ExecutionPlan.master_product_id == master_product_id).order_by(desc(ExecutionPlan.created_at)).limit(max(1, min(limit, 500))).all()
            return {"status": "OK", "version": cls.version, "master_product_id": master_product_id, "count": len(plans), "plans": [cls._plan(row) for row in plans]}
        finally:
            db.close()

    @classmethod
    def _dashboard(cls, product, genome, advertising, search, decisions, plans, metrics):
        scores = cls._genome_scores(genome)
        pending = [d for d in decisions if d.status == "Pending"]
        active_plans = [p for p in plans if p.status in ["Planned", "Ready", "Approved", "Running"]]
        completed = [p for p in plans if p.status in ["DryRunComplete", "Completed", "Executed"]]

        return {
            "health": scores.get("product_health"),
            "sales_30d": metrics.get("sales_30d"),
            "ad_sales_30d": metrics.get("ad_sales_30d"),
            "spend_30d": metrics.get("spend_30d"),
            "acos_pct": metrics.get("acos_pct"),
            "tacos_pct": metrics.get("tacos_pct"),
            "orders_30d": metrics.get("orders_30d"),
            "conversion_rate_pct": metrics.get("conversion_rate_pct"),
            "profit_30d": metrics.get("profit_30d"),
            "margin_pct": metrics.get("margin_pct"),
            "search_health": search.get("search_health") if isinstance(search, dict) else None,
            "advertising_health": advertising.get("advertising_health") if isinstance(advertising, dict) else None,
            "open_tasks": len(pending),
            "active_execution_plans": len(active_plans),
            "completed_execution_plans": len(completed),
            "top_task": pending[0].title if pending else None,
        }

    @classmethod
    def _portfolio_item(cls, db, product: MasterProduct) -> dict[str, Any]:
        channels = db.query(ProductChannel).filter(ProductChannel.master_product_id == product.master_product_id).all()
        genome = db.query(ProductGenome).filter(ProductGenome.master_product_id == product.master_product_id).first()
        pending = db.query(MissionControlDecision).filter(MissionControlDecision.master_product_id == product.master_product_id).filter(MissionControlDecision.status == "Pending").count()
        plans = db.query(ExecutionPlan).filter(ExecutionPlan.master_product_id == product.master_product_id).count()
        metric_result = ProductMetricsService.product_metrics(product.master_product_id)
        metrics = metric_result.get("metrics", {}) if metric_result.get("status") == "OK" else {}

        channel_names = sorted(set([cls._safe_get(c, "channel") for c in channels if cls._safe_get(c, "channel")]))
        marketplaces = sorted(set([cls._safe_get(c, "marketplace") for c in channels if cls._safe_get(c, "marketplace")]))
        scores = cls._genome_scores(genome)

        return {
            "master_product_id": product.master_product_id,
            "product_name": product.name,
            "brand": product.brand,
            "primary_sku": product.primary_sku,
            "product_family": product.product_family,
            "lifecycle_stage": product.lifecycle_stage,
            "status": product.status,
            "channels": channel_names,
            "marketplaces": marketplaces,
            "channel_count": len(channels),
            "health": scores.get("product_health"),
            "ad_sales_30d": metrics.get("ad_sales_30d"),
            "spend_30d": metrics.get("spend_30d"),
            "acos_pct": metrics.get("acos_pct"),
            "orders_30d": metrics.get("orders_30d"),
            "open_decisions": pending,
            "execution_plans": plans,
        }

    @staticmethod
    def _portfolio_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
        with_health = [item for item in items if item.get("health") is not None]
        avg_health = round(sum(item["health"] for item in with_health) / len(with_health)) if with_health else None
        spend = sum(i.get("spend_30d") or 0 for i in items)
        sales = sum(i.get("ad_sales_30d") or 0 for i in items)
        return {
            "products": len(items),
            "average_health": avg_health,
            "ad_sales_30d": round(sales, 2),
            "spend_30d": round(spend, 2),
            "portfolio_acos_pct": round((spend / sales) * 100, 2) if sales else None,
            "products_with_open_decisions": len([i for i in items if (i.get("open_decisions") or 0) > 0]),
            "total_open_decisions": sum(i.get("open_decisions") or 0 for i in items),
            "products_with_execution_plans": len([i for i in items if (i.get("execution_plans") or 0) > 0]),
        }

    @classmethod
    def _workspace_summary(cls, product, genome, advertising, search, decisions, plans, metrics):
        scores = cls._genome_scores(genome)
        return {
            "health": scores.get("product_health"),
            "organic_strength": scores.get("organic_strength"),
            "advertising_dependency": scores.get("advertising_dependency_index"),
            "profitability": scores.get("profitability"),
            "advertising_health": advertising.get("advertising_health") if isinstance(advertising, dict) else None,
            "search_health": search.get("search_health") if isinstance(search, dict) else None,
            "active_tasks": len([d for d in decisions if d.status == "Pending"]),
            "active_execution_plans": len([p for p in plans if p.status in ["Planned", "Ready", "Approved", "Running"]]),
            "top_recommendation": decisions[0].title if decisions else None,
            "sales_30d": metrics.get("sales_30d"),
            "spend_30d": metrics.get("spend_30d"),
            "acos_pct": metrics.get("acos_pct"),
        }

    @staticmethod
    def _safe_get(obj: Any, name: str, default: Any = None) -> Any:
        try:
            return getattr(obj, name)
        except Exception:
            return default

    @classmethod
    def _genome_scores(cls, genome):
        if not genome:
            return {}
        scores = cls._safe_get(genome, "scores")
        if isinstance(scores, dict):
            return {
                "product_health": scores.get("product_health"),
                "organic_strength": scores.get("organic_strength"),
                "advertising_dependency_index": scores.get("advertising_dependency_index"),
                "profitability": scores.get("profitability"),
                "confidence": scores.get("confidence"),
            }
        aliases = {
            "product_health": ["product_health", "health_score", "health"],
            "organic_strength": ["organic_strength", "organic_score"],
            "advertising_dependency_index": ["advertising_dependency_index", "advertising_dependency", "adi"],
            "profitability": ["profitability", "profitability_score", "profit_score"],
            "confidence": ["confidence", "confidence_score"],
        }
        output = {}
        for key, names in aliases.items():
            value = None
            for name in names:
                value = cls._safe_get(genome, name)
                if value is not None:
                    break
            output[key] = value
        return output

    @classmethod
    def _genome_strategy(cls, genome):
        if not genome:
            return {}
        strategy = cls._safe_get(genome, "strategy")
        if isinstance(strategy, dict):
            return strategy
        return {"archetype": cls._safe_get(genome, "archetype"), "objective": cls._safe_get(genome, "objective"), "strategy": cls._safe_get(genome, "recommended_strategy")}

    @classmethod
    def _genome(cls, row):
        if not row:
            return None
        created_at = cls._safe_get(row, "created_at")
        updated_at = cls._safe_get(row, "updated_at")
        signals = cls._safe_get(row, "signals")
        recs = cls._safe_get(row, "recommendations")
        return {
            "master_product_id": cls._safe_get(row, "master_product_id"),
            "scores": cls._genome_scores(row),
            "strategy": cls._genome_strategy(row),
            "signals": signals if isinstance(signals, dict) else {},
            "recommendations": recs if isinstance(recs, list) else [],
            "created_at": created_at.isoformat() if created_at else None,
            "updated_at": updated_at.isoformat() if updated_at else None,
        }

    @staticmethod
    def _advertising(master_product_id: str):
        if not ProductAdvertisingIntelligenceService:
            return {"available": False, "reason": "Product Advertising Intelligence not installed"}
        result = ProductAdvertisingIntelligenceService.product_advertising(master_product_id)
        return result.get("advertising", result)

    @staticmethod
    def _search(master_product_id: str):
        if not ProductSearchIntelligenceService:
            return {"available": False, "reason": "Product Search Intelligence not installed"}
        result = ProductSearchIntelligenceService.product_search(master_product_id)
        return result.get("search", result)

    @staticmethod
    def _product(row):
        return {
            "master_product_id": row.master_product_id,
            "name": row.name,
            "brand": row.brand,
            "product_family": row.product_family,
            "primary_sku": row.primary_sku,
            "ean_upc": row.ean_upc,
            "status": row.status,
            "lifecycle_stage": row.lifecycle_stage,
            "active": row.active,
            "notes": row.notes,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @classmethod
    def _channel(cls, row):
        raw = cls._safe_get(row, "raw")
        raw = raw if isinstance(raw, dict) else {}

        def first_attr_or_raw(*names):
            for name in names:
                value = cls._safe_get(row, name)
                if value is not None:
                    return value
                if raw.get(name) is not None:
                    return raw.get(name)
            return None

        return {
            "id": cls._safe_get(row, "id"),
            "master_product_id": cls._safe_get(row, "master_product_id"),
            "channel": first_attr_or_raw("channel", "platform"),
            "marketplace": first_attr_or_raw("marketplace", "marketplace_id", "country_code"),
            "sku": first_attr_or_raw("sku", "seller_sku", "merchant_sku"),
            "asin": first_attr_or_raw("asin", "amazon_asin"),
            "listing_id": first_attr_or_raw("listing_id", "etsy_listing_id", "shopify_product_id", "external_id"),
            "product_url": first_attr_or_raw("product_url", "url", "listing_url"),
            "status": first_attr_or_raw("status", "state") or "unknown",
            "raw": raw,
        }

    @staticmethod
    def _decision(row):
        return {
            "decision_id": row.decision_id,
            "master_product_id": row.master_product_id,
            "product_name": row.product_name,
            "title": row.title,
            "category": row.category,
            "priority": row.priority,
            "status": row.status,
            "estimated_monthly_impact": row.estimated_monthly_impact,
            "confidence": row.confidence,
            "urgency": row.urgency,
            "recommendation": row.recommendation,
            "reason": row.reason,
            "why_now": row.why_now,
            "evidence": row.evidence,
            "source": row.source,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def _plan(row):
        return {
            "plan_id": row.plan_id,
            "decision_id": row.decision_id,
            "master_product_id": row.master_product_id,
            "product_name": row.product_name,
            "platform": row.platform,
            "action_type": row.action_type,
            "title": row.title,
            "status": row.status,
            "risk_level": row.risk_level,
            "expected_monthly_impact": row.expected_monthly_impact,
            "confidence": row.confidence,
            "rollback_available": row.rollback_available,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def _result(row):
        return {
            "result_id": row.result_id,
            "plan_id": row.plan_id,
            "decision_id": row.decision_id,
            "platform": row.platform,
            "action_type": row.action_type,
            "status": row.status,
            "success": row.success,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def _event(row):
        return {
            "event_id": row.event_id,
            "event_type": row.event_type,
            "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
            "title": row.title,
            "description": row.description,
            "source": row.source,
            "payload": row.payload,
        }
