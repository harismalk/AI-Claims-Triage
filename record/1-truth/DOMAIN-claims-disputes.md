---
id: DOMAIN-claims-disputes
status: current
covers: []
---
# DOMAIN-claims-disputes · Glossary and dispute types

## Terms

| Term | Meaning here |
|---|---|
| Claim | A provider's bill to the insurer for a service to a member |
| Denial | The insurer refused to pay a claim, with a reason code |
| Dispute | A member's or provider's challenge to a claim decision |
| Tier-1 dispute | Routine, high-volume, usually checkable from data |
| Adjuster | The human who decides disputes today |
| Reversal | Overturning a denial and paying the claim |
| Adjustment | Changing the paid amount (e.g. refunding an overcharged copay) |
| Copay | Fixed member charge per service type, defined by the plan |
| In/out of network | Whether a provider has a contract with the insurer |

## Dispute types

| Type | Reason code | Auto-resolve eligible? | Key evidence |
|---|---|---|---|
| Duplicate denial | `DUP` | Yes, under the limit | Similar claims: same member, provider, procedure; compare service dates and visit IDs |
| Billing error | `BIL` | Yes, under the limit | Plan copay rules vs. amount charged |
| Missing documents | `DOC` | Yes, if documents are on file | Document log timestamps vs. denial date |
| Coverage denial | `COV` | **No, always escalate** | Plan coverage rules; requires human judgment |

## Authority limit

Auto-resolve limit: **$500** per dispute (configurable). Above it, always escalate.
