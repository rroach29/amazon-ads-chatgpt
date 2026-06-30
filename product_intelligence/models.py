"""Business OS v8.7 — Product Intelligence domain models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ProductIdentity:
    asin: str | None = None
    sku: str | None = None
    title: str | None = None
    product_type: str | None = None
    channel: str = "amazon"
    country_code: str | None = None
    marketplace: str | None = None
    currency: str | None = None

    def key(self) -> str:
        return self.asin or self.sku or "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProductRevenueProfile:
    total_revenue: float = 0.0
    paid_revenue: float = 0.0
    organic_revenue: float = 0.0
    organic_ratio: float | None = None
    paid_ratio: float | None = None
    ad_spend: float = 0.0
    tacos: float | None = None
    orders: int = 0
    units_ordered: int = 0
    sessions: int = 0
    page_views: int = 0
    buy_box_percentage: float | None = None
    confidence: int = 0
    basis: str = "awaiting_seller_central_data"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProductProfitProfile:
    estimated_cogs: float = 0.0
    estimated_shipping: float = 0.0
    estimated_amazon_fees: float = 0.0
    estimated_gross_profit: float = 0.0
    contribution_profit: float = 0.0
    gross_margin: float | None = None
    contribution_margin: float | None = None
    profit_score: int = 0
    economics_basis: str = "heuristic_or_catalog_estimate"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProductAdvertisingProfile:
    paid_revenue_available: bool = False
    direct_asin_attribution_available: bool = False
    note: str = "Current Ads reports are campaign/search-term based; direct ASIN attribution is limited until ASIN/SKU ad mapping is added."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProductListingProfile:
    title_present: bool = False
    asin_present: bool = False
    sku_present: bool = False
    listing_quality_score: int = 0
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProductHealthProfile:
    revenue_score: int = 0
    organic_score: int = 0
    conversion_score: int = 0
    profit_score: int = 0
    listing_score: int = 0
    customer_score: int = 50
    growth_score: int = 0
    overall_score: int = 0
    status: str = "UNKNOWN"
    priorities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProductTimelineEvent:
    date: str | None
    event_type: str
    title: str
    metrics: dict[str, Any] = field(default_factory=dict)
    source: str = "business_os"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
