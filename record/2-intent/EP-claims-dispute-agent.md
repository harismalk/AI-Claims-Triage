---
id: EP-claims-dispute-agent
status: active
owner: Harry Malik
---
# EP-claims-dispute-agent · Tier-1 claims-dispute agent

## Problem

A health insurer's adjusters handle a high volume of routine (tier-1) claim disputes:
duplicate denials, copay/billing errors, missing-document denials, and coverage
denials. Each one takes 20–40 minutes, and most of that time is *assembling context*
across a 15-year-old claims system, not deciding. The insurer wants an agent that
does the investigation, resolves the provably-safe cases, and hands adjusters a
pre-assembled case for everything else.

The insurer, members, and data are fictional. All data is synthetic.

## Users

| User | Needs |
|---|---|
| Adjuster | A queue of disputes with evidence already gathered and a recommendation they can accept or override in one click |
| Claims ops lead | Confidence the agent never acts outside its authority; a weekly view of volume, auto-resolve rate, override rate |
| Member | A correct, clear resolution letter, faster |

## Outcome milestones

Milestones are outcomes, not dates.

| ID | Outcome | Measured by |
|---|---|---|
| M1 | The agent resolves safe disputes correctly and never exceeds its authority | Decision accuracy on the golden set; zero safety-invariant violations |
| M2 | Adjusters start from an assembled case instead of a blank screen | Every escalated dispute carries a recommendation and linked evidence |
| M3 | The system gets measurably better from adjuster corrections | Overrides become eval cases; scores on those cases rise with no regressions |

## Non-goals

- Coverage *decisions* by the agent. Coverage disputes always escalate.
- Real insurer integrations, real PHI, or real payments.
- A polished multi-page UI. One adjuster-queue screen and one eval view.

## Related

- Engineering plan: [[PS-mvp]]
- Architecture: [[ARCH-system-overview]]
- Domain glossary: [[DOMAIN-claims-disputes]]
