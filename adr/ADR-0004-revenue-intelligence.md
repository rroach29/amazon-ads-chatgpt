# ADR-0004: Revenue Intelligence

## Status
Accepted

## Context
Amazon Ads reports provide paid attributed sales, but they do not provide total business revenue. To compare organic sales vs paid advertising, Business OS needs Seller Central Sales & Traffic data from SP-API.

## Decision
Create a Revenue Intelligence subsystem that reconciles Seller Central total revenue with Amazon Ads paid attributed revenue. Organic revenue is calculated as total revenue minus paid attributed revenue.

## Consequences
- Adds a new `seller_central_sales_traffic` table for SP-API report ingestion.
- Revenue endpoints work before SP-API is connected by returning clear `AWAITING_SELLER_CENTRAL_DATA` status.
- Multi-channel revenue can be added later without changing Mission Control concepts.

## Formula

`organic_revenue = total_revenue - paid_attributed_revenue`

`TACOS = ad_spend / total_revenue`
