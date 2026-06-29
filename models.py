from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Boolean, Text, JSON
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

class CampaignDailyDetail(Base):
    __tablename__ = "campaign_daily_details"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, index=True)
    channel = Column(String, index=True, default="amazon_ads")
    campaign_id = Column(String, index=True)
    campaign_name = Column(String)
    campaign_status = Column(String)
    impressions = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    spend = Column(Float, default=0)
    sales = Column(Float, default=0)
    orders = Column(Integer, default=0)
    acos = Column(Float)
    roas = Column(Float)
    ctr = Column(Float)
    cpc = Column(Float)
    conversion_rate = Column(Float)
    raw = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


class SearchTermDailyDetail(Base):
    __tablename__ = "search_term_daily_details"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, index=True)
    channel = Column(String, index=True, default="amazon_ads")
    campaign_id = Column(String, index=True)
    campaign_name = Column(String)
    ad_group_id = Column(String)
    ad_group_name = Column(String)
    keyword_id = Column(String)
    keyword = Column(String)
    match_type = Column(String)
    search_term = Column(String, index=True)
    impressions = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    spend = Column(Float, default=0)
    sales = Column(Float, default=0)
    orders = Column(Integer, default=0)
    acos = Column(Float)
    roas = Column(Float)
    ctr = Column(Float)
    cpc = Column(Float)
    conversion_rate = Column(Float)
    raw = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

class OptimizationQueue(Base):
    __tablename__ = "optimization_queue"

    id = Column(Integer, primary_key=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    channel = Column(String, default="amazon_ads")
    status = Column(String, default="PENDING")

    priority = Column(String)
    recommendation_type = Column(String)

    campaign_id = Column(String, nullable=True)
    campaign_name = Column(String, nullable=True)

    ad_group_id = Column(String, nullable=True)
    ad_group_name = Column(String, nullable=True)

    search_term = Column(String, nullable=True)
    keyword = Column(String, nullable=True)

    title = Column(String)
    reason = Column(Text)

    recommended_action = Column(String)
    confidence = Column(Float, default=0)
    estimated_monthly_savings = Column(Float, default=0)

    payload = Column(JSON)

    approved_at = Column(DateTime, nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    executed_at = Column(DateTime, nullable=True)

    execution_result = Column(JSON, nullable=True)

class DecisionHistory(Base):
    __tablename__ = "decision_history"

    id = Column(Integer, primary_key=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    evaluated_at = Column(DateTime, nullable=True)

    channel = Column(String, index=True, default="amazon_ads")

    decision = Column(String, index=True)
    priority = Column(String, index=True)
    confidence = Column(Float, default=0)
    risk = Column(String)

    recommended_action = Column(String)
    reasoning = Column(JSON)
    payload = Column(JSON)

    estimated_monthly_impact = Column(Float, default=0)

    status = Column(String, index=True, default="OPEN")
    outcome = Column(String, nullable=True)

    actual_impact = Column(Float, nullable=True)
    was_correct = Column(Boolean, nullable=True)

    notes = Column(Text, nullable=True)
