# ADR-0007 — SP-API Live Connection

## Status
Accepted

## Context
Business OS v8.8 established the SP-API scaffold and manual Sales & Traffic ingestion. After adding the seller refresh token in Render, diagnostics confirmed that LWA credentials are configured. The next step is to safely test live SP-API connectivity.

SP-API endpoint calls require two layers of authorization:

1. Login with Amazon access token created from the seller refresh token.
2. AWS Signature Version 4 signing for SP-API data-plane requests.

## Decision
Add a live connection layer that:

- Exchanges the seller refresh token for a short-lived LWA access token.
- Detects AWS SigV4 credential readiness without exposing secrets.
- Signs SP-API requests when SigV4 credentials are available.
- Exposes Swagger-safe diagnostics and auth test endpoints.
- Keeps Sales & Traffic report generation as the first live data workflow.

## Consequences
Business OS can now distinguish between:

- Missing SP-API configuration.
- LWA token failure.
- Missing AWS SigV4 credentials.
- SP-API seller authorization/role errors.
- Successfully authenticated Seller Central access.

This avoids blind 403 errors and makes SP-API onboarding manageable from Swagger.
