---
id: ARCH-system-overview
status: proposed
covers: []
---
# ARCH-system-overview · How the system fits together

Status is `proposed` until CP3 lands. Update this doc whenever the code diverges
from it; set `covers:` to the code paths it describes once they exist, so the
validator can flag it when they change.

## Flow

```
dispute → router (code) → specialist agent (LLM + tools) → proposal
        → decision gate (code) → auto-resolve  ─┐
                                → adjuster queue ┤→ write via legacy API → trace
adjuster override → effect diff → grouped failure → new golden case
```

## Components

| Component | Responsibility | LLM? |
|---|---|---|
| Legacy system | Postgres with legacy schema + a clunky write API. The thing we integrate with, not the thing we own | No |
| Tool runtime | Wraps every tool call. Modes: live, replay. Effect log + overlay for writes outside live | No |
| Tools | Clean typed functions over the legacy system | No |
| Router | Picks the specialist from reason code + rules; LLM fallback only when rules can't decide | Fallback only |
| Specialists | One per dispute type; own prompt, tools, knowledge file; output a structured proposal | Yes |
| Decision gate | Verifies the proposal's evidence and applies authority limits | No |
| Letter drafter | Writes the member letter from the final decision | Yes |
| Evals | Golden set from the answer key, code scorers, invariants, calibrated judge | Judge only |
| API + UI | Adjuster queue, case view, accept/override | No |

## Boundaries

- The LLM never decides its own authority. The gate does.
- Specialists never write. They propose; executors write after the gate.
- Nothing outside the tool runtime touches the legacy system.

## Decisions

- [[DEC-0001-propose-gate-execute]]
- [[DEC-0002-deterministic-router]]
- [[DEC-0003-project-record]]
