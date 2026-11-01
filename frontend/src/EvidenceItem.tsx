import { useState } from "react";
import { ClaimView, formatCents, getClaim } from "./api";

/** One evidence claim ID. Clicking it opens the underlying claim record. */
export function EvidenceItem({ claimId }: { claimId: number }) {
  const [claim, setClaim] = useState<ClaimView | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    if (!claim) {
      try {
        setClaim(await getClaim(claimId));
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        return;
      }
    }
    setOpen(true);
  }

  return (
    <div className="evidence-item">
      <button className="evidence-link" onClick={toggle}>
        claim #{claimId} {open ? "▾" : "▸"}
      </button>
      {error && <p className="error">{error}</p>}
      {open && claim && (
        <dl className="claim-record">
          <dt>Procedure</dt>
          <dd>{claim.procedure_code}</dd>
          <dt>Date of service</dt>
          <dd>{claim.date_of_service}</dd>
          <dt>Status</dt>
          <dd>{claim.status_description ?? claim.status_code}</dd>
          <dt>Billed amount</dt>
          <dd>{formatCents(claim.billed_amount_cents)}</dd>
          <dt>Paid amount</dt>
          <dd>{formatCents(claim.paid_amount_cents)}</dd>
          {claim.denial_reason_description && (
            <>
              <dt>Denial reason</dt>
              <dd>{claim.denial_reason_description}</dd>
            </>
          )}
        </dl>
      )}
    </div>
  );
}
