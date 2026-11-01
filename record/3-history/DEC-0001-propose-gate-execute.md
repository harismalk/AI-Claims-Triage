---
id: DEC-0001-propose-gate-execute
date: 2026-11-01
status: accepted
---
# DEC-0001 · The agent proposes, code verifies, executors write

## Context
Agents can be convincing and wrong, and can talk themselves into approving work.
Disputes move real money in the scenario.

## Decision
Specialist agents only produce structured proposals. A deterministic decision gate
re-checks every cited record against the database and applies authority limits.
Only executors behind the gate call write tools.

## Consequences
- The LLM can't exceed its authority, even if prompt-injected.
- Offline evals grade proposals directly; only executors need write interception.
- Cost: a proposal schema to maintain, and a gate that must stay in sync with dispute types.
