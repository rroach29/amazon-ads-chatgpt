# ADR-0001 — Decision Provenance

## Status
Accepted for Business OS v8.3.

## Context
Generated decisions were carrying `optimizer_name: unknown` even when their source opportunities correctly identified the optimizer. This weakened learning analytics, optimizer scorecards, and future planning.

## Decision
Every decision now receives a `DecisionProvenance` object from `DecisionFactory`. Provenance includes optimizer name, version, class, Business OS version, decision factory version, data context, business objective, and source opportunity ID.

## Consequences
Planning and analytics can group decisions by true source. Existing clients remain compatible because provenance is additive and legacy decision dictionaries are preserved.
