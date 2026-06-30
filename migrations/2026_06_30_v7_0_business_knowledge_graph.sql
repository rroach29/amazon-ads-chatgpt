-- Business OS v7.0 — Business Knowledge Graph
-- Optional foundational tables for persistent relationships.
-- Current v7.0 routes can run without this migration because they build the graph
-- from existing dashboard/report/decision tables. Apply this migration when you
-- are ready to persist custom product/entity relationships.

CREATE TABLE IF NOT EXISTS business_graph_nodes (
    id SERIAL PRIMARY KEY,
    node_key VARCHAR(255) UNIQUE NOT NULL,
    node_type VARCHAR(80) NOT NULL,
    label VARCHAR(255) NOT NULL,
    source VARCHAR(80) DEFAULT 'business_os',
    attributes JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_business_graph_nodes_type ON business_graph_nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_business_graph_nodes_source ON business_graph_nodes(source);

CREATE TABLE IF NOT EXISTS business_graph_edges (
    id SERIAL PRIMARY KEY,
    source_node_key VARCHAR(255) NOT NULL,
    target_node_key VARCHAR(255) NOT NULL,
    relationship VARCHAR(100) NOT NULL,
    weight DOUBLE PRECISION DEFAULT 1.0,
    evidence JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_node_key, target_node_key, relationship)
);

CREATE INDEX IF NOT EXISTS idx_business_graph_edges_source ON business_graph_edges(source_node_key);
CREATE INDEX IF NOT EXISTS idx_business_graph_edges_target ON business_graph_edges(target_node_key);
CREATE INDEX IF NOT EXISTS idx_business_graph_edges_relationship ON business_graph_edges(relationship);
