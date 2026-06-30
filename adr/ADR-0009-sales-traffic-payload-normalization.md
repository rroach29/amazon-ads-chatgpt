# ADR-0009 — Sales & Traffic Payload Normalization

## Status
Accepted

## Context
Swagger users may provide dates in browser-friendly formats such as `MM/DD/YYYY` and marketplace aliases like `CA` or `US`. Amazon SP-API Reports API requires RFC3339 `dataStartTime` / `dataEndTime` and canonical Amazon marketplace IDs.

## Decision
Normalize Sales & Traffic report requests before calling Amazon:

- parse ISO, `YYYY-MM-DD`, `MM/DD/YYYY`, and `YYYY/MM/DD`
- emit UTC RFC3339 timestamps
- map `US`, `CA`, and `MX` to their marketplace IDs
- fail locally with clear messages before calling Amazon when values are invalid

## Consequences
This keeps Swagger easy to use while preserving strict SP-API payload correctness.
