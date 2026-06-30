# ADR-0010 — Seller Central Automation and Organic vs Paid Reconciliation

## Status
Accepted

## Context
Business OS v8.9 proved that the platform can request, poll, download, parse, and ingest live SP-API Sales & Traffic reports. The next step is to make this repeatable and expose organic-vs-paid revenue as a first-class executive KPI.

## Decision
Add a Seller Central automation service that reuses the existing SPAPIReportPipelineService rather than duplicating report logic. Add RevenueReconciliationService to combine Seller Central total revenue with Amazon Ads paid-attributed revenue.

## Consequences
- Seller Central ingestion can be run as a safe Swagger action today and later wired into APScheduler.
- Revenue Intelligence gains executive organic-vs-paid endpoints.
- Mission Control can consume a stable reconciliation contract in future releases.
- No SQL migration is required because v8.9 already added the SPAPIReportJob table and seller_central_sales_traffic exists.
