# Billing-error knowledge

Dispute type `BIL`. The member is disputing the amount they were charged for
a claim.

## How to check it

1. Look up the disputed claim's procedure code and find its service type
   (the mapping from procedure code to service type, e.g. `99213` ->
   `primary_care_visit`, is in `app.generate_data.PROC_CATALOG` -- it is
   reference data, not something you compute).
2. Look up the member's plan (`get_member` for their plan code, then
   `get_plan_terms` for that plan's copay schedule).
3. Compare the claim's billed amount against that plan's copay for that
   service type.

## Deciding

- **Billed amount > plan's copay for that service type:** the member was
  overcharged. **Reverse**, amount = billed amount minus the plan copay (the
  overage, to be refunded).
- **Billed amount == plan's copay:** correctly charged. **Deny**, amount $0.
- **No copay defined for that service type under the member's plan:** you
  can't resolve this from the plan terms alone. **Escalate** for a human to
  check.

## Evidence and rationale

Cite the disputed claim. Your rationale must name the specific rule you
used: the plan code, the service type, and the copay amount it defines --
not just "I checked the plan."
