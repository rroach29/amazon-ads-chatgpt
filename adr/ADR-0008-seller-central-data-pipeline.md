# ADR-0008 — Seller Central Data Pipeline

## Status

Accepted

## Context

Revenue Intelligence needs Seller Central Sales & Traffic data to calculate total revenue, sessions, conversion, and organic versus paid sales. v8.8/v8.8.1 proved SP-API credentials, LWA token exchange, SigV4 signing, and marketplace participation.

## Decision

Introduce a persistent SP-API report job table and pipeline service for `GET_SALES_AND_TRAFFIC_REPORT`.

The pipeline lifecycle is:

1. Request report.
2. Store report job and report ID.
3. Poll processing status.
4. Download report document once ready.
5. Ingest rows into `seller_central_sales_traffic`.
6. Preserve job history for diagnostics and future schedulers.

## Consequences

- Revenue Intelligence can move from manual import to automated Seller Central ingestion.
- Future scheduler jobs can reuse the same pipeline service.
- The system gains traceability for report requests, failures, and downloaded data.
- Additional SP-API report families can follow the same pattern.
