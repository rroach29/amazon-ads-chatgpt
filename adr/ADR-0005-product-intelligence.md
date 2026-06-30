# ADR-0005 — Product Intelligence as the Primary Business Object

## Status
Accepted

## Context
Business OS has matured from Amazon Ads reporting into an AI operating layer with revenue, profit, planning, provenance, and optimizer services. The next strategic shift is to make the product/ASIN the primary business object rather than campaign, keyword, or marketplace metrics.

## Decision
Introduce Product Intelligence as a dedicated domain service. It creates Product 360 profiles that combine product identity, Seller Central revenue, estimated product economics, listing foundations, health scoring, and timeline events.

## Consequences
- Listing Intelligence, Finance Intelligence, Growth Intelligence, Creative Intelligence, and Customer Intelligence can enrich a shared product object.
- Mission Control can prioritize product-level actions instead of isolated campaign-level recommendations.
- Product-level paid attribution remains conservative until ASIN/SKU-level ads attribution is added.

## Follow-ups
- Add ASIN/SKU ad attribution mapping.
- Add real listing metadata, image, A+ content, review, and pricing signals.
- Integrate Product Health into Executive Planning.
