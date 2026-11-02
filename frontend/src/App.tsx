import { useEffect, useState } from "react";
import { CaseDetail, DisputeSummary, decideCase, formatCents, getCase, listDisputes } from "./api";
import { GateActionBadge, ReasonBadge } from "./Badge";
import { EvidenceItem } from "./EvidenceItem";

export default function App() {
  const [disputes, setDisputes] = useState<DisputeSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [caseDetail, setCaseDetail] = useState<CaseDetail | null>(null);
  const [overriding, setOverriding] = useState(false);
  const [overrideDecision, setOverrideDecision] = useState<"reverse" | "deny">("reverse");
  const [overrideAmount, setOverrideAmount] = useState("");
  const [overrideReason, setOverrideReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [queueLoading, setQueueLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  async function refreshQueue() {
    setQueueLoading(true);
    try {
      setDisputes(await listDisputes());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setQueueLoading(false);
    }
  }

  useEffect(() => {
    refreshQueue();
  }, []);

  async function selectDispute(disputeId: number) {
    setSelectedId(disputeId);
    setOverriding(false);
    setOverrideAmount("");
    setOverrideReason("");
    setError(null);
    try {
      setCaseDetail(await getCase(disputeId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function accept() {
    if (!selectedId) return;
    setError(null);
    setSubmitting(true);
    try {
      await decideCase(selectedId, { action: "accept" });
      setSelectedId(null);
      setCaseDetail(null);
      await refreshQueue();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  async function submitOverride() {
    if (!selectedId) return;
    setError(null);
    setSubmitting(true);
    const amountCents = overrideDecision === "deny" ? 0 : Math.round(parseFloat(overrideAmount || "0") * 100);
    try {
      await decideCase(selectedId, {
        action: "override",
        decision: overrideDecision,
        amount_cents: amountCents,
        reason: overrideReason,
      });
      setSelectedId(null);
      setCaseDetail(null);
      setOverriding(false);
      await refreshQueue();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-brand">
          <span className="topbar-mark">CD</span>
          Claims Dispute Adjuster Console
        </div>
        <div className="topbar-meta">{queueLoading ? "Loading…" : `${disputes.length} open dispute${disputes.length === 1 ? "" : "s"}`}</div>
      </header>

      <div className="app-body">
        <aside className="queue">
          <div className="queue-header">
            <h1>Adjuster queue</h1>
            <div className="queue-count">
              {queueLoading ? "Loading…" : `${disputes.length} awaiting review`}
            </div>
          </div>

          {queueLoading && (
            <div>
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="skeleton-item" />
              ))}
            </div>
          )}

          {!queueLoading && disputes.length === 0 && <div className="queue-empty">No open disputes. Queue is clear.</div>}

          {!queueLoading && disputes.length > 0 && (
            <ul className="queue-list">
              {disputes.map((d) => (
                <li key={d.dispute_id}>
                  <button
                    className={d.dispute_id === selectedId ? "queue-item selected" : "queue-item"}
                    onClick={() => selectDispute(d.dispute_id)}
                  >
                    <div className="queue-item-row">
                      <span className="queue-item-id">#{d.dispute_id}</span>
                      <ReasonBadge reasonCode={d.reason_code} />
                    </div>
                    <div className="queue-item-rec">
                      <span
                        className={
                          "queue-item-decision " + (d.recommended_decision ?? "none")
                        }
                      >
                        {d.recommended_decision ?? "no recommendation"}
                      </span>
                      {d.recommended_amount_cents !== null && (
                        <span className="queue-item-amount">{formatCents(d.recommended_amount_cents)}</span>
                      )}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <main className="case-panel">
          <div className="case-panel-inner">
            {error && <p className="error-banner">{error}</p>}

            {!caseDetail && (
              <div className="empty-state">
                <div className="empty-state-icon">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
                    <path
                      d="M9 2h6a1 1 0 0 1 1 1v1h1a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h1V3a1 1 0 0 1 1-1Z"
                      strokeLinejoin="round"
                    />
                    <path d="M9 11h6M9 15h6M9 7h2" strokeLinecap="round" />
                  </svg>
                </div>
                <p>Select a dispute from the queue to review it.</p>
              </div>
            )}

            {caseDetail && (
              <div>
                <div className="case-header">
                  <div>
                    <h2 className="case-title">
                      <span className="case-id">#{caseDetail.dispute_id}</span>
                      {caseDetail.reason_description ?? caseDetail.reason_code}
                    </h2>
                    <p className="case-filed-date">Filed {caseDetail.filed_date}</p>
                  </div>
                  <ReasonBadge reasonCode={caseDetail.reason_code} />
                </div>

                <div className="complaint-card">
                  <div className="complaint-card-label">Member complaint</div>
                  <p>{caseDetail.complaint_text}</p>
                </div>

                <section className="section">
                  <h3 className="section-title">Agent recommendation</h3>
                  {caseDetail.recommended_decision ? (
                    <div className={`recommendation-card ${caseDetail.gate_action ?? ""}`.trim()}>
                      <div className="recommendation-headline">
                        <span className="recommendation-decision">{caseDetail.recommended_decision}</span>
                        <span className="recommendation-amount">
                          {formatCents(caseDetail.recommended_amount_cents)}
                        </span>
                        <GateActionBadge action={caseDetail.gate_action} />
                      </div>
                      <p className="recommendation-rationale">{caseDetail.recommended_rationale}</p>
                      <ul className="gate-reasons">
                        {caseDetail.gate_reasons.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  ) : (
                    <div className="recommendation-none">
                      No specialist recommendation exists for this dispute type — an adjuster must decide manually.
                    </div>
                  )}
                </section>

                <section className="section">
                  <h3 className="section-title">Evidence</h3>
                  {caseDetail.recommended_evidence_claim_ids.length === 0 ? (
                    <p className="no-evidence">No evidence cited.</p>
                  ) : (
                    <div className="evidence-list">
                      {caseDetail.recommended_evidence_claim_ids.map((claimId) => (
                        <EvidenceItem key={claimId} claimId={claimId} />
                      ))}
                    </div>
                  )}
                </section>

                <section className="section">
                  <h3 className="section-title">Decision</h3>
                  {!overriding && (
                    <div className="decision-buttons">
                      <button
                        className="btn btn-primary"
                        disabled={!caseDetail.recommended_decision || submitting}
                        onClick={accept}
                      >
                        Accept recommendation
                      </button>
                      <button className="btn btn-secondary" disabled={submitting} onClick={() => setOverriding(true)}>
                        Override
                      </button>
                    </div>
                  )}
                  {overriding && (
                    <div className="override-form">
                      <div className="form-field">
                        <label className="form-label">Decision</label>
                        <div className="segmented">
                          <button
                            type="button"
                            className={overrideDecision === "reverse" ? "active" : ""}
                            onClick={() => setOverrideDecision("reverse")}
                          >
                            Reverse (pay)
                          </button>
                          <button
                            type="button"
                            className={overrideDecision === "deny" ? "active" : ""}
                            onClick={() => setOverrideDecision("deny")}
                          >
                            Deny (uphold)
                          </button>
                        </div>
                      </div>
                      {overrideDecision === "reverse" && (
                        <div className="form-field">
                          <label className="form-label">Amount</label>
                          <div className="amount-input-wrap">
                            <span className="prefix">$</span>
                            <input
                              type="number"
                              step="0.01"
                              min="0"
                              placeholder="0.00"
                              value={overrideAmount}
                              onChange={(e) => setOverrideAmount(e.target.value)}
                            />
                          </div>
                        </div>
                      )}
                      <div className="form-field">
                        <label className="form-label">Reason</label>
                        <textarea
                          placeholder="Why does this decision differ from the agent's recommendation?"
                          value={overrideReason}
                          onChange={(e) => setOverrideReason(e.target.value)}
                        />
                      </div>
                      <div className="override-form-actions">
                        <button
                          className="btn btn-primary"
                          onClick={submitOverride}
                          disabled={!overrideReason || submitting}
                        >
                          Submit override
                        </button>
                        <button className="btn btn-ghost" disabled={submitting} onClick={() => setOverriding(false)}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </section>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
