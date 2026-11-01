# Duplicate-denial knowledge

Dispute type `DUP`. The legacy system denied a claim because it matched it
against another claim for the same member and provider and flagged it as a
duplicate. Your job is to decide whether that match was actually a duplicate.

## How to tell a genuine duplicate from a false positive

- **Genuine duplicate** -- the matched claim is for the **same procedure
  code**. Billing sometimes resubmits the same service, occasionally days
  apart, so don't require the same date. Correct decision: **deny**, amount
  $0.
- **False positive** -- the matched claim is for a **different procedure
  code**. Two different procedures performed at the same visit, even on the
  exact same date, are not a duplicate; `VISIT_ID` just groups claims from one
  visit, it does not mean they're the same service. This is the trap: do not
  use "same date" as your test for duplicate -- use the procedure code.
  Correct decision: **reverse**, amount = the disputed claim's billed amount.

## Evidence

Always cite the disputed claim and whichever claim `find_similar_claims`
matched it against -- that pairing is the entire basis for the original
(right or wrong) denial.

`find_similar_claims` can return more than one candidate, including a claim
that merely happens to share the same procedure code somewhere else and has
nothing to do with this denial. The claim actually being compared against is
the one sharing this claim's `VISIT_ID` -- prefer that one over any other
coincidental match.
