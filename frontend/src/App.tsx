import { useEffect, useState } from "react";
import { CaseDetail, DisputeSummary, decideCase, formatCents, getCase, listDisputes } from "./api";
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
    try {
      await decideCase(selectedId, { action: "accept" });
      setSelectedId(null);
      setCaseDetail(null);
      await refreshQueue();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function submitOverride() {
    if (!selectedId) return;
    setError(null);
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
    }
  }

  return (
    <div className="app">
      <aside className="queue">
        <h1>Adjuster queue</h1>
        {queueLoading && <p>Loading…</p>}
        <ul>
          {disputes.map((d) => (
            <li key={d.dispute_id}>
              <button
                className={d.dispute_id === selectedId ? "queue-item selected" : "queue-item"}
                onClick={() => selectDispute(d.dispute_id)}
              >
                <span className="dispute-id">#{d.dispute_id}</span>
                <span className="reason-code">{d.reason_code}</span>
                <span className="recommendation">
                  {d.recommended_decision
                    ? `${d.recommended_decision} ${formatCents(d.recommended_amount_cents)} (${d.gate_action})`
                    : "no recommendation"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <main className="case-panel">
        {error && <p className="error">{error}</p>}
        {!caseDetail && <p>Select a dispute from the queue.</p>}
        {caseDetail && (
          <div className="case-summary">
            <h2>
              Dispute #{caseDetail.dispute_id} — {caseDetail.reason_description ?? caseDetail.reason_code}
            </h2>
            <p className="filed-date">Filed {caseDetail.filed_date}</p>
            <blockquote className="complaint-text">{caseDetail.complaint_text}</blockquote>

            <section className="recommendation-box">
              <h3>Agent recommendation</h3>
              {caseDetail.recommended_decision ? (
                <>
                  <p>
                    <strong>{caseDetail.recommended_decision}</strong>{" "}
                    {formatCents(caseDetail.recommended_amount_cents)} — gate: {caseDetail.gate_action}
                  </p>
                  <p className="rationale">{caseDetail.recommended_rationale}</p>
                  <ul className="gate-reasons">
                    {caseDetail.gate_reasons.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </>
              ) : (
                <p>No specialist recommendation for this dispute type -- adjuster must decide manually.</p>
              )}
            </section>

            <section className="evidence-box">
              <h3>Evidence</h3>
              {caseDetail.recommended_evidence_claim_ids.length === 0 && <p>No evidence cited.</p>}
              {caseDetail.recommended_evidence_claim_ids.map((claimId) => (
                <EvidenceItem key={claimId} claimId={claimId} />
              ))}
            </section>

            <section className="decision-box">
              <h3>Decision</h3>
              {!overriding && (
                <div className="decision-buttons">
                  <button disabled={!caseDetail.recommended_decision} onClick={accept}>
                    Accept recommendation
                  </button>
                  <button onClick={() => setOverriding(true)}>Override</button>
                </div>
              )}
              {overriding && (
                <div className="override-form">
                  <label>
                    Decision
                    <select
                      value={overrideDecision}
                      onChange={(e) => setOverrideDecision(e.target.value as "reverse" | "deny")}
                    >
                      <option value="reverse">Reverse (pay)</option>
                      <option value="deny">Deny (uphold)</option>
                    </select>
                  </label>
                  {overrideDecision === "reverse" && (
                    <label>
                      Amount ($)
                      <input
                        type="number"
                        step="0.01"
                        value={overrideAmount}
                        onChange={(e) => setOverrideAmount(e.target.value)}
                      />
                    </label>
                  )}
                  <label>
                    Reason
                    <textarea value={overrideReason} onChange={(e) => setOverrideReason(e.target.value)} />
                  </label>
                  <div className="decision-buttons">
                    <button onClick={submitOverride} disabled={!overrideReason}>
                      Submit override
                    </button>
                    <button onClick={() => setOverriding(false)}>Cancel</button>
                  </div>
                </div>
              )}
            </section>
          </div>
        )}
      </main>
    </div>
  );
}
