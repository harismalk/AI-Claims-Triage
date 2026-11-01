---
id: DEC-0002-deterministic-router
date: 2026-11-01
status: accepted
---
# DEC-0002 · Routing is code; specialists hold the domain reasoning

## Context
One agent with every dispute type's knowledge risks cross-contaminating rules
between types (Meta's thin-orchestrator post reports exactly this failure mode).

## Decision
A deterministic router picks the specialist from the reason code and rules. An LLM
classifier runs only as a logged fallback when the reason code is missing or
contradicts the complaint. Each specialist loads only its own knowledge.

## Consequences
- Routing is testable and auditable; failures attribute to one specialist.
- Adding a dispute type means adding a specialist and a routing rule, not editing a mega-prompt.
- Cost: misfiled reason codes need the fallback path.
