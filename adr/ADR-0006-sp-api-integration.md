# ADR-0006: SP-API Integration as Seller Central Data Source

## Status
Accepted

## Context
Business OS can now analyze advertising, revenue, profit, and products, but organic-vs-paid intelligence requires Seller Central total business data. Amazon Ads provides paid attributed revenue; Seller Central Sales & Traffic reports provide total revenue, sessions, page views, units ordered, and Buy Box metrics.

## Decision
Introduce an SP-API integration package focused first on the Reports API and `GET_SALES_AND_TRAFFIC_REPORT`. The first implementation supports configuration diagnostics, report request/status/collection workflow, and manual Sales & Traffic JSON ingestion for early testing before live credentials are fully enabled.

## Consequences
Revenue Intelligence can be populated from Seller Central data without redesign. Listing, Finance, Growth, and Product Intelligence can later build on the same SP-API foundation. Future hardening should add AWS SigV4 signing credentials, persistent report job tracking, scheduled ingestion, Catalog API, Listings Items API, Orders API, and Finances API.
