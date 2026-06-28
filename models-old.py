from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Boolean, JSON
from database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, unique=True, index=True)
    asin = Column(String, index=True)
    shopify_product_id = Column(String, index=True)
    title = Column(String)
    product_type = Column(String)
    cost = Column(Float, default=0)
    shipping_cost = Column(Float, default=0)
    amazon_fee_estimate = Column(Float, default=0)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AdCampaign(Base):
    __tablename__ = "ad_campaigns"

    id = Column(Integer, primary_key=True, index=True)
    channel = Column(String, index=True)
    campaign_id = Column(String, index=True)
    campaign_name = Column(String)
    status = Column(String)
    budget = Column(Float)
    campaign_type = Column(String)
    raw = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


class AdMetricsDaily(Base):
    __tablename__ = "ad_metrics_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, index=True)
    channel = Column(String, index=True)
    campaign_id = Column(String, index=True)
    campaign_name = Column(String)
    impressions = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    spend = Column(Float, default=0)
    sales = Column(Float, default=0)
    orders = Column(Integer, default=0)
    acos = Column(Float)
    roas = Column(Float)
    cpc = Column(Float)
    ctr = Column(Float)
    conversion_rate = Column(Float)
    raw = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


class SearchTermDaily(Base):
    __tablename__ = "search_terms_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, index=True)
    channel = Column(String, index=True)
    campaign_id = Column(String, index=True)
    campaign_name = Column(String)
    search_term = Column(String, index=True)
    keyword = Column(String)
    match_type = Column(String)
    clicks = Column(Integer, default=0)
    impressions = Column(Integer, default=0)
    spend = Column(Float, default=0)
    sales = Column(Float, default=0)
    orders = Column(Integer, default=0)
    acos = Column(Float)
    roas = Column(Float)
    raw = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


class DailyDashboard(Base):
    __tablename__ = "daily_dashboards"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, unique=True, index=True)
    channel = Column(String, index=True)
    spend = Column(Float, default=0)
    sales = Column(Float, default=0)
    acos = Column(Float)
    roas = Column(Float)
    clicks = Column(Integer, default=0)
    impressions = Column(Integer, default=0)
    orders = Column(Integer, default=0)
    health_score = Column(Integer)
    alerts = Column(JSON)
    recommendations = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, index=True)
    channel = Column(String, index=True)
    priority = Column(String)
    type = Column(String)
    campaign_id = Column(String)
    campaign_name = Column(String)
    search_term = Column(String)
    recommendation = Column(String)
    status = Column(String, default="open")
    raw = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

class ScheduledReportJob(Base):
    __tablename__ = "scheduled_report_jobs"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, index=True)
    campaign_report_id = Column(String, index=True)
    search_term_report_id = Column(String, index=True)
    status = Column(String, default="PENDING")
    created_at = Column(DateTime, default=datetime.utcnow)
