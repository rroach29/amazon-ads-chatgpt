# ADR-0003 — Profit Intelligence

## Status
Accepted

## Context
The Business OS can already reason about spend, sales, ACOS, ROAS, decisions, optimizers, learning, and executive plans. However, it cannot yet evaluate whether advertising decisions make the business more profitable.

## Decision
Introduce a Profit Intelligence subsystem that estimates contribution profit from sales, ad spend, and configurable economic assumptions. The first implementation is heuristic-safe and additive. It does not require Seller Central order economics or product/SKU mapping.

## Consequences
- Mission Control and Executive Briefing can expose estimated profit signals.
- Future optimizers can move from ACOS/ROAS optimization toward profit optimization.
- Real fee, COGS, shipping, returns, and inventory costs can replace fallback assumptions later.

## Alternatives Considered
- Wait for Seller Central economics before adding profit: rejected because platform-level profit contracts can be added now.
- Embed profit calculations in optimizers: rejected because profit should be a shared business service.
