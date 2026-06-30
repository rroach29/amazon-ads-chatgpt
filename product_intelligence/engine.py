"""Business OS v8.7 — Product Intelligence Engine.

Product Intelligence makes the product/ASIN the primary business object. It
combines Seller Central revenue data, product catalog economics, and current
Business OS intelligence into Product 360 profiles.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from database import SessionLocal
from models import Product, SellerCentralSalesTraffic
from business_data_context import resolve_data_context, apply_date_context, apply_marketplace_context
from product_intelligence.models import (
    ProductAdvertisingProfile,
    ProductHealthProfile,
    ProductIdentity,
    ProductListingProfile,
    ProductProfitProfile,
    ProductRevenueProfile,
    ProductTimelineEvent,
)


class ProductIntelligenceEngine:
    version = "8.7"

    @staticmethod
    def diagnostics() -> dict[str, Any]:
        db = SessionLocal()
        try:
            product_count = db.query(Product).count()
            seller_rows = db.query(SellerCentralSalesTraffic).count()
            return {
                "status": "OK",
                "version": ProductIntelligenceEngine.version,
                "checks": {
                    "database": "OK",
                    "product_catalog": "OK",
                    "seller_central_sales_traffic": "OK",
                    "product_360_engine": "OK",
                },
                "counts": {
                    "products": product_count,
                    "seller_central_sales_traffic_rows": seller_rows,
                },
                "capabilities": [
                    "product_360",
                    "product_health_score",
                    "product_revenue_profile",
                    "product_profit_profile",
                    "product_timeline",
                    "listing_quality_foundation",
                    "multi_channel_ready_product_identity",
                ],
                "seller_central_data_status": "OK" if seller_rows else "AWAITING_SELLER_CENTRAL_DATA",
            }
        except Exception as exc:
            return {"status": "ERROR", "version": ProductIntelligenceEngine.version, "message": str(exc)}
        finally:
            db.close()

    @staticmethod
    def list_products(
        window: str = "latest",
        country_code: str | None = None,
        profile_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        context = resolve_data_context(window=window, country_code=country_code, profile_id=profile_id)
        db = SessionLocal()
        try:
            profiles = ProductIntelligenceEngine._build_profiles(db, context)
            items = [ProductIntelligenceEngine._compact_product(profile) for profile in profiles]
            items.sort(
                key=lambda item: (
                    item.get("health", {}).get("overall_score") or 0,
                    item.get("revenue", {}).get("total_revenue") or 0,
                ),
                reverse=True,
            )
            limited = items[: max(1, min(limit, 250))]
            return {
                "status": "OK",
                "version": ProductIntelligenceEngine.version,
                "data_context": context,
                "count": len(limited),
                "total_products_detected": len(items),
                "products": limited,
                "top_products": limited[:10],
                "products_needing_attention": [item for item in limited if item.get("health", {}).get("overall_score", 0) < 60][:10],
                "seller_central_data_status": "OK" if ProductIntelligenceEngine._has_revenue_data(profiles) else "AWAITING_SELLER_CENTRAL_DATA",
                "narrative": ProductIntelligenceEngine._portfolio_narrative(limited),
            }
        finally:
            db.close()

    @staticmethod
    def product_360(
        asin: str,
        window: str = "latest",
        country_code: str | None = None,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        context = resolve_data_context(window=window, country_code=country_code, profile_id=profile_id)
        db = SessionLocal()
        try:
            profile = ProductIntelligenceEngine._find_profile(db, context, asin)
            if not profile:
                return {
                    "status": "NOT_FOUND",
                    "version": ProductIntelligenceEngine.version,
                    "asin": asin,
                    "data_context": context,
                    "message": "No product catalog or Seller Central Sales & Traffic rows were found for this ASIN/SKU.",
                }
            result = ProductIntelligenceEngine._full_product(profile)
            result["status"] = "OK"
            result["version"] = ProductIntelligenceEngine.version
            result["data_context"] = context
            result["executive_summary"] = ProductIntelligenceEngine._product_narrative(result)
            return result
        finally:
            db.close()

    @staticmethod
    def product_health(asin: str, window: str = "latest", country_code: str | None = None, profile_id: str | None = None) -> dict[str, Any]:
        product = ProductIntelligenceEngine.product_360(asin=asin, window=window, country_code=country_code, profile_id=profile_id)
        if product.get("status") != "OK":
            return product
        return {
            "status": "OK",
            "version": ProductIntelligenceEngine.version,
            "identity": product.get("identity"),
            "health": product.get("health"),
            "priorities": product.get("health", {}).get("priorities", []),
        }

    @staticmethod
    def product_revenue(asin: str, window: str = "latest", country_code: str | None = None, profile_id: str | None = None) -> dict[str, Any]:
        product = ProductIntelligenceEngine.product_360(asin=asin, window=window, country_code=country_code, profile_id=profile_id)
        if product.get("status") != "OK":
            return product
        return {"status": "OK", "version": ProductIntelligenceEngine.version, "identity": product.get("identity"), "revenue": product.get("revenue")}

    @staticmethod
    def product_profit(asin: str, window: str = "latest", country_code: str | None = None, profile_id: str | None = None) -> dict[str, Any]:
        product = ProductIntelligenceEngine.product_360(asin=asin, window=window, country_code=country_code, profile_id=profile_id)
        if product.get("status") != "OK":
            return product
        return {"status": "OK", "version": ProductIntelligenceEngine.version, "identity": product.get("identity"), "profit": product.get("profit")}

    @staticmethod
    def product_listing(asin: str, window: str = "latest", country_code: str | None = None, profile_id: str | None = None) -> dict[str, Any]:
        product = ProductIntelligenceEngine.product_360(asin=asin, window=window, country_code=country_code, profile_id=profile_id)
        if product.get("status") != "OK":
            return product
        return {"status": "OK", "version": ProductIntelligenceEngine.version, "identity": product.get("identity"), "listing": product.get("listing")}

    @staticmethod
    def product_timeline(
        asin: str,
        window: str = "latest",
        country_code: str | None = None,
        profile_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        product = ProductIntelligenceEngine.product_360(asin=asin, window=window, country_code=country_code, profile_id=profile_id)
        if product.get("status") != "OK":
            return product
        timeline = product.get("timeline", [])[: max(1, min(limit, 250))]
        return {"status": "OK", "version": ProductIntelligenceEngine.version, "identity": product.get("identity"), "count": len(timeline), "timeline": timeline}

    @staticmethod
    def _build_profiles(db, context: dict[str, Any]) -> list[dict[str, Any]]:
        catalog = ProductIntelligenceEngine._catalog_by_key(db)
        seller_rows = ProductIntelligenceEngine._seller_rows(db, context)
        grouped = defaultdict(list)
        for row in seller_rows:
            key = ProductIntelligenceEngine._product_key(row.asin, row.sku)
            grouped[key].append(row)

        keys = set(catalog.keys()) | set(grouped.keys())
        profiles = []
        for key in keys:
            rows = grouped.get(key, [])
            catalog_product = catalog.get(key)
            profiles.append(ProductIntelligenceEngine._profile_from_sources(key, catalog_product, rows))
        return profiles

    @staticmethod
    def _find_profile(db, context: dict[str, Any], asin_or_sku: str) -> dict[str, Any] | None:
        target = str(asin_or_sku or "").strip().lower()
        for profile in ProductIntelligenceEngine._build_profiles(db, context):
            identity = profile.get("identity", {})
            if str(identity.get("asin") or "").lower() == target or str(identity.get("sku") or "").lower() == target:
                return profile
        return None

    @staticmethod
    def _catalog_by_key(db) -> dict[str, Product]:
        result = {}
        for product in db.query(Product).all():
            key = ProductIntelligenceEngine._product_key(product.asin, product.sku)
            result[key] = product
        return result

    @staticmethod
    def _seller_rows(db, context: dict[str, Any]):
        query = db.query(SellerCentralSalesTraffic)
        query = apply_date_context(query, SellerCentralSalesTraffic, context)
        query = apply_marketplace_context(query, SellerCentralSalesTraffic, context)
        return query.all()

    @staticmethod
    def _profile_from_sources(key: str, catalog_product: Product | None, rows: list[SellerCentralSalesTraffic]) -> dict[str, Any]:
        latest = rows[-1] if rows else None
        asin = (latest.asin if latest else None) or (catalog_product.asin if catalog_product else None)
        sku = (latest.sku if latest else None) or (catalog_product.sku if catalog_product else None)
        title = (latest.title if latest and latest.title else None) or (catalog_product.title if catalog_product else None)
        country_code = latest.country_code if latest else None
        marketplace = latest.marketplace if latest else None
        currency = latest.currency if latest else None
        identity = ProductIdentity(
            asin=asin,
            sku=sku,
            title=title,
            product_type=catalog_product.product_type if catalog_product else None,
            country_code=country_code,
            marketplace=marketplace,
            currency=currency,
        )
        revenue = ProductIntelligenceEngine._revenue_profile(rows, currency)
        profit = ProductIntelligenceEngine._profit_profile(revenue, catalog_product)
        listing = ProductIntelligenceEngine._listing_profile(identity)
        advertising = ProductAdvertisingProfile()
        timeline = ProductIntelligenceEngine._timeline(rows, catalog_product)
        health = ProductIntelligenceEngine._health_profile(revenue, profit, listing)
        return {
            "identity": identity.to_dict(),
            "revenue": revenue.to_dict(),
            "profit": profit.to_dict(),
            "advertising": advertising.to_dict(),
            "listing": listing.to_dict(),
            "health": health.to_dict(),
            "timeline": [event.to_dict() for event in timeline],
        }

    @staticmethod
    def _revenue_profile(rows: list[SellerCentralSalesTraffic], currency: str | None) -> ProductRevenueProfile:
        total = sum(ProductIntelligenceEngine._safe_float(row.ordered_product_sales) for row in rows)
        orders = sum(ProductIntelligenceEngine._safe_int(row.total_order_items) for row in rows)
        units = sum(ProductIntelligenceEngine._safe_int(row.units_ordered) for row in rows)
        sessions = sum(ProductIntelligenceEngine._safe_int(row.sessions) for row in rows)
        page_views = sum(ProductIntelligenceEngine._safe_int(row.page_views) for row in rows)
        buy_box_values = [ProductIntelligenceEngine._safe_float(row.buy_box_percentage) for row in rows if row.buy_box_percentage is not None]
        buy_box = round(sum(buy_box_values) / len(buy_box_values), 4) if buy_box_values else None
        # Product-level paid attributed revenue requires ASIN/SKU ad attribution. Until that mapping exists,
        # keep paid revenue conservative and mark confidence accordingly.
        paid = 0.0
        organic = max(total - paid, 0.0)
        paid_ratio = paid / total if total else None
        organic_ratio = organic / total if total else None
        confidence = 60 if total > 0 else 0
        return ProductRevenueProfile(
            total_revenue=round(total, 2),
            paid_revenue=round(paid, 2),
            organic_revenue=round(organic, 2),
            organic_ratio=round(organic_ratio, 4) if organic_ratio is not None else None,
            paid_ratio=round(paid_ratio, 4) if paid_ratio is not None else None,
            ad_spend=0.0,
            tacos=None,
            orders=orders,
            units_ordered=units,
            sessions=sessions,
            page_views=page_views,
            buy_box_percentage=buy_box,
            confidence=confidence,
            basis="seller_central_product_revenue_pending_asin_ad_attribution" if total else "awaiting_seller_central_data",
        )

    @staticmethod
    def _profit_profile(revenue: ProductRevenueProfile, catalog_product: Product | None) -> ProductProfitProfile:
        sales = ProductIntelligenceEngine._safe_float(revenue.total_revenue)
        units = ProductIntelligenceEngine._safe_int(revenue.units_ordered)
        orders = ProductIntelligenceEngine._safe_int(revenue.orders)
        if catalog_product:
            cogs = units * ProductIntelligenceEngine._safe_float(catalog_product.cost)
            shipping = orders * ProductIntelligenceEngine._safe_float(catalog_product.shipping_cost)
            amazon_fees = orders * ProductIntelligenceEngine._safe_float(catalog_product.amazon_fee_estimate)
            basis = "product_catalog_unit_economics"
        else:
            cogs = sales * 0.12
            shipping = sales * 0.08
            amazon_fees = sales * 0.15
            basis = "heuristic_default"
        gross_profit = sales - cogs - shipping - amazon_fees
        contribution_profit = gross_profit - ProductIntelligenceEngine._safe_float(revenue.ad_spend)
        gross_margin = gross_profit / sales if sales else None
        contribution_margin = contribution_profit / sales if sales else None
        score = ProductIntelligenceEngine._profit_score(contribution_profit, contribution_margin, sales)
        return ProductProfitProfile(
            estimated_cogs=round(cogs, 2),
            estimated_shipping=round(shipping, 2),
            estimated_amazon_fees=round(amazon_fees, 2),
            estimated_gross_profit=round(gross_profit, 2),
            contribution_profit=round(contribution_profit, 2),
            gross_margin=round(gross_margin, 4) if gross_margin is not None else None,
            contribution_margin=round(contribution_margin, 4) if contribution_margin is not None else None,
            profit_score=score,
            economics_basis=basis,
        )

    @staticmethod
    def _listing_profile(identity: ProductIdentity) -> ProductListingProfile:
        recommendations = []
        title_present = bool(identity.title)
        asin_present = bool(identity.asin)
        sku_present = bool(identity.sku)
        score = 40
        if title_present:
            score += 30
            title_length = len(identity.title or "")
            if 50 <= title_length <= 180:
                score += 15
            else:
                recommendations.append("Review title length and keyword coverage.")
        else:
            recommendations.append("Add or import product title for listing intelligence.")
        if asin_present:
            score += 10
        else:
            recommendations.append("Add ASIN to enable Amazon product intelligence.")
        if sku_present:
            score += 5
        if not recommendations:
            recommendations.append("Listing foundation looks usable. Add image, A+ and review data next for deeper listing intelligence.")
        return ProductListingProfile(
            title_present=title_present,
            asin_present=asin_present,
            sku_present=sku_present,
            listing_quality_score=int(max(0, min(score, 100))),
            recommendations=recommendations,
        )

    @staticmethod
    def _timeline(rows: list[SellerCentralSalesTraffic], catalog_product: Product | None) -> list[ProductTimelineEvent]:
        events = []
        if catalog_product and catalog_product.created_at:
            events.append(ProductTimelineEvent(date=str(catalog_product.created_at.date()), event_type="PRODUCT_CATALOG", title="Product added to Business OS catalog", source="products"))
        for row in sorted(rows, key=lambda item: item.date or ""):
            revenue = ProductIntelligenceEngine._safe_float(row.ordered_product_sales)
            events.append(ProductTimelineEvent(
                date=str(row.date) if row.date else None,
                event_type="REVENUE_OBSERVATION",
                title=f"Seller Central revenue observed: {revenue:.2f}",
                metrics={
                    "ordered_product_sales": round(revenue, 2),
                    "units_ordered": ProductIntelligenceEngine._safe_int(row.units_ordered),
                    "sessions": ProductIntelligenceEngine._safe_int(row.sessions),
                    "page_views": ProductIntelligenceEngine._safe_int(row.page_views),
                    "buy_box_percentage": row.buy_box_percentage,
                },
                source="seller_central_sales_traffic",
            ))
        return list(reversed(events))

    @staticmethod
    def _health_profile(revenue: ProductRevenueProfile, profit: ProductProfitProfile, listing: ProductListingProfile) -> ProductHealthProfile:
        revenue_score = ProductIntelligenceEngine._revenue_score(revenue)
        organic_score = ProductIntelligenceEngine._organic_score(revenue)
        conversion_score = ProductIntelligenceEngine._conversion_score(revenue)
        profit_score = profit.profit_score
        listing_score = listing.listing_quality_score
        growth_score = int(round((revenue_score + organic_score + conversion_score) / 3))
        components = [revenue_score, organic_score, conversion_score, profit_score, listing_score, 50, growth_score]
        overall = int(round(sum(components) / len(components)))
        priorities = []
        if revenue.confidence == 0:
            priorities.append("Connect or import Seller Central Sales & Traffic data for product-level revenue intelligence.")
        if listing_score < 70:
            priorities.append("Improve product identity/listing data before deeper listing optimization.")
        if profit_score < 50 and revenue.total_revenue > 0:
            priorities.append("Review product economics, price, shipping, or ad dependency because profit score is weak.")
        if conversion_score < 50 and revenue.sessions > 0:
            priorities.append("Investigate conversion rate, listing quality, pricing, or reviews.")
        status = "STRONG" if overall >= 80 else "WATCH" if overall >= 60 else "NEEDS_ATTENTION"
        return ProductHealthProfile(
            revenue_score=revenue_score,
            organic_score=organic_score,
            conversion_score=conversion_score,
            profit_score=profit_score,
            listing_score=listing_score,
            customer_score=50,
            growth_score=growth_score,
            overall_score=overall,
            status=status,
            priorities=priorities or ["No urgent product-level issue detected with current data."],
        )

    @staticmethod
    def _compact_product(profile: dict[str, Any]) -> dict[str, Any]:
        return {
            "identity": profile.get("identity"),
            "revenue": profile.get("revenue"),
            "profit": profile.get("profit"),
            "health": profile.get("health"),
            "listing": profile.get("listing"),
        }

    @staticmethod
    def _full_product(profile: dict[str, Any]) -> dict[str, Any]:
        return dict(profile)

    @staticmethod
    def _portfolio_narrative(items: list[dict[str, Any]]) -> str:
        if not items:
            return "Product Intelligence is installed, but no product catalog or Seller Central product revenue rows were found."
        top = items[0]
        identity = top.get("identity", {})
        health = top.get("health", {})
        return f"Top product signal is {identity.get('title') or identity.get('asin') or identity.get('sku') or 'unknown product'} with product health score {health.get('overall_score')}."

    @staticmethod
    def _product_narrative(product: dict[str, Any]) -> str:
        identity = product.get("identity", {})
        revenue = product.get("revenue", {})
        profit = product.get("profit", {})
        health = product.get("health", {})
        name = identity.get("title") or identity.get("asin") or identity.get("sku") or "This product"
        return (
            f"{name} has product health score {health.get('overall_score')} with total revenue "
            f"{revenue.get('total_revenue')} and estimated contribution profit {profit.get('contribution_profit')}."
        )

    @staticmethod
    def _has_revenue_data(profiles: list[dict[str, Any]]) -> bool:
        return any((profile.get("revenue", {}).get("total_revenue") or 0) > 0 for profile in profiles)

    @staticmethod
    def _product_key(asin: str | None, sku: str | None) -> str:
        if asin:
            return f"asin:{str(asin).strip().lower()}"
        if sku:
            return f"sku:{str(sku).strip().lower()}"
        return "unknown"

    @staticmethod
    def _revenue_score(revenue: ProductRevenueProfile) -> int:
        if revenue.total_revenue <= 0:
            return 0
        return int(max(0, min(100, 45 + revenue.total_revenue / 20)))

    @staticmethod
    def _organic_score(revenue: ProductRevenueProfile) -> int:
        if revenue.total_revenue <= 0:
            return 0
        ratio = revenue.organic_ratio if revenue.organic_ratio is not None else 0
        return int(max(0, min(100, 35 + ratio * 65)))

    @staticmethod
    def _conversion_score(revenue: ProductRevenueProfile) -> int:
        if revenue.sessions <= 0:
            return 35 if revenue.orders > 0 else 0
        conversion = revenue.orders / revenue.sessions
        return int(max(0, min(100, 35 + conversion * 600)))

    @staticmethod
    def _profit_score(contribution_profit: float, contribution_margin: float | None, sales: float) -> int:
        if sales <= 0:
            return 0
        margin_component = 0 if contribution_margin is None else max(-30, min(contribution_margin * 100, 60))
        profit_component = max(-20, min(contribution_profit / 10, 30))
        return int(max(0, min(round(50 + margin_component + profit_component), 100)))

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value if value is not None else default)
        except Exception:
            return default

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value if value is not None else default)
        except Exception:
            return default
