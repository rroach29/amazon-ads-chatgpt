# ADR-0002: Executive Planning Engine

## Status
Accepted

## Context
Mission Control and optimizers can generate decisions, but executive work needs a plan composed of initiatives and action groups rather than isolated recommendations.

## Decision
Introduce an additive Executive Planning Engine that consumes optimizer outputs and typed domain models to create Plan, Initiative, and ActionGroup objects. The engine does not execute actions; it preserves the existing approval and execution workflow.

## Consequences
- Mission Control can evolve from priority lists toward coherent executive plans.
- Optimizer outputs remain independent.
- Conflict detection can happen before approval.
- No database migration is required for this phase.
