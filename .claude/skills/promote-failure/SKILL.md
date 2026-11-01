---
name: promote-failure
description: Turn a production failure or adjuster override into a reproducible golden eval case with its recorded tool outputs and data snapshot. Use when an agent decision was wrong and should never regress again. Requires CP2 runtime and CP4 eval harness.
---

A promoted case must replay identically months later, so it bundles three things:

| Part | Source |
|---|---|
| Input | The dispute as the agent saw it |
| Recorded tool outputs | The trace's tool calls and results, from the tool runtime |
| Data snapshot | The DB rows the tools read, as of the trace timestamp |

## Steps
1. Locate the trace and the override (what the agent proposed, what the adjuster chose, and why).
2. Classify the root cause before writing anything:
   - **Agent reasoning**: the evidence was available and the agent concluded wrongly.
   - **Tool or data gap**: the agent couldn't have seen the right evidence.
   - **Ambiguous**: reasonable adjusters would disagree. Do not promote; flag for a human.
3. Write the bundle into the golden set with the corrected expected answer and a
   `source: override` tag plus the override ID.
4. Run the case in replay mode and confirm it **fails** on the current agent. A case
   that already passes is not testing the failure.
5. If fixing it now, use `execute-ticket` on a new ticket; otherwise leave it failing
   in a tracked `known-failures` group so CI reports it without blocking.
6. Note the root-cause class in the agent journal if it reveals a pattern.
