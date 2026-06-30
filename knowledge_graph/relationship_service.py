"""
Business OS v7.0 — Relationship Service

Builds a first-generation business knowledge graph from the existing Amazon Ads
reporting database. The service is intentionally read-only and safe: it does not
change campaigns, decisions, budgets, or report data.

Current graph:
Business -> Marketplace -> Campaign -> Ad Group -> Keyword -> Search Term
                            \-> Decision History

Future graph extensions:
Product, SKU/ASIN, inventory, margin, Shopify, Etsy, Meta, Google Ads, finance,
operations, and manufacturing nodes can plug into this same contract.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from database import SessionLocal
from models import CampaignDailyDetail, DailyDashboard, DecisionHistory, SearchTermDailyDetail

from .relationship_models import BusinessEdge, BusinessNode, KnowledgeGraphSnapshot


class RelationshipService:
    DEFAULT_LIMIT = 250

    @staticmethod
    def _safe_str(value: Any, fallback: str = "unknown") -> str:
        if value is None or value == "":
            return fallback
        return str(value)

    @staticmethod
    def _node_key(node_type: str, value: Any) -> str:
        return f"{node_type}:{RelationshipService._safe_str(value)}"

    @staticmethod
    def _latest_date(db, country_code: str | None = None, profile_id: str | None = None):
        query = db.query(DailyDashboard).filter(DailyDashboard.channel == "amazon_ads")
        if profile_id:
            query = query.filter(DailyDashboard.profile_id == str(profile_id))
        elif country_code:
            query = query.filter(DailyDashboard.country_code == str(country_code).upper())
        latest = query.order_by(DailyDashboard.date.desc(), DailyDashboard.created_at.desc()).first()
        return latest.date if latest else date.today()

    @staticmethod
    def build_graph(
        country_code: str | None = None,
        profile_id: str | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        db = SessionLocal()
        node_map: dict[str, BusinessNode] = {}
        edge_map: dict[tuple[str, str, str], BusinessEdge] = {}

        def add_node(node: BusinessNode):
            node_map[node.node_id] = node

        def add_edge(edge: BusinessEdge):
            edge_map[(edge.source_id, edge.target_id, edge.relationship)] = edge

        try:
            latest_date = RelationshipService._latest_date(db, country_code, profile_id)
            scope = {
                "channel": "amazon_ads",
                "date": str(latest_date),
                "country_code": str(country_code).upper() if country_code else None,
                "profile_id": str(profile_id) if profile_id else None,
                "limit": limit,
            }

            business_id = "business:root"
            add_node(BusinessNode(business_id, "business", "Business", "business_os"))

            dashboards = db.query(DailyDashboard).filter(
                DailyDashboard.channel == "amazon_ads",
                DailyDashboard.date == latest_date,
            )
            if profile_id:
                dashboards = dashboards.filter(DailyDashboard.profile_id == str(profile_id))
            elif country_code:
                dashboards = dashboards.filter(DailyDashboard.country_code == str(country_code).upper())

            for row in dashboards.all():
                marketplace_label = row.marketplace or row.country_code or row.profile_id or "Amazon Ads"
                marketplace_id = RelationshipService._node_key("marketplace", row.profile_id or marketplace_label)
                add_node(BusinessNode(
                    marketplace_id,
                    "marketplace",
                    marketplace_label,
                    "amazon_ads",
                    {
                        "profile_id": row.profile_id,
                        "country_code": row.country_code,
                        "currency": row.currency,
                        "spend": row.spend,
                        "sales": row.sales,
                        "acos": row.acos,
                        "roas": row.roas,
                        "orders": row.orders,
                        "health_score": row.health_score,
                    },
                ))
                add_edge(BusinessEdge(business_id, marketplace_id, "HAS_MARKETPLACE"))

            campaigns = db.query(CampaignDailyDetail).filter(
                CampaignDailyDetail.channel == "amazon_ads",
                CampaignDailyDetail.date == latest_date,
            )
            if profile_id:
                campaigns = campaigns.filter(CampaignDailyDetail.profile_id == str(profile_id))
            elif country_code:
                campaigns = campaigns.filter(CampaignDailyDetail.country_code == str(country_code).upper())
            campaigns = campaigns.order_by(CampaignDailyDetail.spend.desc()).limit(limit).all()

            for row in campaigns:
                marketplace_id = RelationshipService._node_key("marketplace", row.profile_id or row.marketplace or row.country_code)
                campaign_id = RelationshipService._node_key("campaign", row.campaign_id)
                add_node(BusinessNode(
                    campaign_id,
                    "campaign",
                    row.campaign_name or RelationshipService._safe_str(row.campaign_id, "Unnamed Campaign"),
                    "amazon_ads",
                    {
                        "campaign_id": row.campaign_id,
                        "status": row.campaign_status,
                        "profile_id": row.profile_id,
                        "country_code": row.country_code,
                        "marketplace": row.marketplace,
                        "currency": row.currency,
                        "spend": row.spend,
                        "sales": row.sales,
                        "acos": row.acos,
                        "roas": row.roas,
                        "orders": row.orders,
                        "clicks": row.clicks,
                        "impressions": row.impressions,
                    },
                ))
                add_edge(BusinessEdge(marketplace_id, campaign_id, "HAS_CAMPAIGN", evidence={"date": str(latest_date)}))

            search_terms = db.query(SearchTermDailyDetail).filter(
                SearchTermDailyDetail.channel == "amazon_ads",
                SearchTermDailyDetail.date == latest_date,
            )
            if profile_id:
                search_terms = search_terms.filter(SearchTermDailyDetail.profile_id == str(profile_id))
            elif country_code:
                search_terms = search_terms.filter(SearchTermDailyDetail.country_code == str(country_code).upper())
            search_terms = search_terms.order_by(SearchTermDailyDetail.spend.desc()).limit(limit).all()

            for row in search_terms:
                campaign_id = RelationshipService._node_key("campaign", row.campaign_id)
                ad_group_id = RelationshipService._node_key("ad_group", row.ad_group_id or f"{row.campaign_id}:unknown")
                keyword_id = RelationshipService._node_key("keyword", row.keyword_id or row.keyword or f"{row.ad_group_id}:unknown")
                term_id = RelationshipService._node_key("search_term", row.search_term)

                add_node(BusinessNode(ad_group_id, "ad_group", row.ad_group_name or "Unknown Ad Group", "amazon_ads", {
                    "ad_group_id": row.ad_group_id,
                    "campaign_id": row.campaign_id,
                    "campaign_name": row.campaign_name,
                }))
                add_node(BusinessNode(keyword_id, "keyword", row.keyword or "Unknown Keyword", "amazon_ads", {
                    "keyword_id": row.keyword_id,
                    "match_type": row.match_type,
                    "ad_group_id": row.ad_group_id,
                    "campaign_id": row.campaign_id,
                }))
                add_node(BusinessNode(term_id, "search_term", row.search_term or "Unknown Search Term", "amazon_ads", {
                    "campaign_id": row.campaign_id,
                    "campaign_name": row.campaign_name,
                    "ad_group_id": row.ad_group_id,
                    "keyword_id": row.keyword_id,
                    "spend": row.spend,
                    "sales": row.sales,
                    "acos": row.acos,
                    "roas": row.roas,
                    "orders": row.orders,
                    "clicks": row.clicks,
                    "impressions": row.impressions,
                }))
                add_edge(BusinessEdge(campaign_id, ad_group_id, "HAS_AD_GROUP"))
                add_edge(BusinessEdge(ad_group_id, keyword_id, "HAS_KEYWORD"))
                add_edge(BusinessEdge(keyword_id, term_id, "MATCHED_SEARCH_TERM", evidence={
                    "date": str(latest_date),
                    "spend": row.spend,
                    "sales": row.sales,
                    "orders": row.orders,
                }))

            decisions = db.query(DecisionHistory).filter(DecisionHistory.channel == "amazon_ads")
            decisions = decisions.order_by(DecisionHistory.created_at.desc()).limit(limit).all()
            for row in decisions:
                payload = row.payload if isinstance(row.payload, dict) else {}
                raw = row.raw if isinstance(row.raw, dict) else {}
                campaign_ref = payload.get("campaign_id") or raw.get("campaign_id")
                if not campaign_ref:
                    continue
                campaign_id = RelationshipService._node_key("campaign", campaign_ref)
                decision_id = RelationshipService._node_key("decision", row.id)
                add_node(BusinessNode(decision_id, "decision", row.decision or f"Decision {row.id}", "business_os", {
                    "decision_id": row.id,
                    "decision": row.decision,
                    "status": getattr(row, "status", None),
                    "confidence": getattr(row, "confidence", None),
                    "estimated_monthly_impact": getattr(row, "estimated_monthly_impact", None),
                    "risk": getattr(row, "risk", None),
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }))
                add_edge(BusinessEdge(campaign_id, decision_id, "HAS_DECISION"))

            nodes = list(node_map.values())
            edges = list(edge_map.values())
            by_type = defaultdict(int)
            for node in nodes:
                by_type[node.node_type] += 1
            by_relationship = defaultdict(int)
            for edge in edges:
                by_relationship[edge.relationship] += 1

            snapshot = KnowledgeGraphSnapshot.build(
                scope=scope,
                nodes=nodes,
                edges=edges,
                summary={
                    "node_count": len(nodes),
                    "edge_count": len(edges),
                    "nodes_by_type": dict(by_type),
                    "edges_by_relationship": dict(by_relationship),
                },
            )
            return snapshot.to_dict()
        finally:
            db.close()

    @staticmethod
    def campaign_context(campaign_id: str) -> dict[str, Any]:
        graph = RelationshipService.build_graph(limit=500)
        target = RelationshipService._node_key("campaign", campaign_id)
        nodes = {node["id"]: node for node in graph.get("nodes", [])}
        connected_edges = [
            edge for edge in graph.get("edges", [])
            if edge.get("source") == target or edge.get("target") == target
        ]
        connected_node_ids = {target}
        for edge in connected_edges:
            connected_node_ids.add(edge.get("source"))
            connected_node_ids.add(edge.get("target"))
        return {
            "status": "OK" if target in nodes else "NOT_FOUND",
            "campaign_id": campaign_id,
            "campaign_node": nodes.get(target),
            "connected_nodes": [nodes[node_id] for node_id in connected_node_ids if node_id in nodes],
            "relationships": connected_edges,
        }

    @staticmethod
    def search_term_context(search_term: str) -> dict[str, Any]:
        graph = RelationshipService.build_graph(limit=500)
        term_key = RelationshipService._node_key("search_term", search_term)
        nodes = {node["id"]: node for node in graph.get("nodes", [])}
        upstream = []
        for edge in graph.get("edges", []):
            if edge.get("target") == term_key:
                upstream.append(edge)
        return {
            "status": "OK" if term_key in nodes else "NOT_FOUND",
            "search_term": search_term,
            "search_term_node": nodes.get(term_key),
            "upstream_relationships": upstream,
        }
