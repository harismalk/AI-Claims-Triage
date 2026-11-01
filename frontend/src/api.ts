// Matches app/api.py's Pydantic response models exactly.

export const API_BASE = "http://localhost:8000";

export interface DisputeSummary {
  dispute_id: number;
  reason_code: string;
  filed_date: string;
  status_code: string;
  recommended_decision: "reverse" | "deny" | null;
  recommended_amount_cents: number | null;
  gate_action: "auto_resolve" | "escalate" | null;
}

export interface ClaimView {
  claim_id: number;
  member_id: number;
  provider_id: number;
  date_of_service: string;
  submit_date: string;
  procedure_code: string;
  status_code: string;
  status_description: string | null;
  billed_amount_cents: number;
  paid_amount_cents: number | null;
  denial_reason_code: string | null;
  denial_reason_description: string | null;
  secondary_denial_reason_code: string | null;
  secondary_denial_reason_description: string | null;
  visit_group_id: string | null;
  note: string | null;
}

export interface CaseDetail {
  dispute_id: number;
  reason_code: string;
  reason_description: string | null;
  filed_date: string;
  status_code: string;
  complaint_text: string | null;
  claim: ClaimView;
  recommended_decision: "reverse" | "deny" | null;
  recommended_amount_cents: number | null;
  recommended_rationale: string | null;
  recommended_evidence_claim_ids: number[];
  gate_action: "auto_resolve" | "escalate" | null;
  gate_reasons: string[];
}

export interface DecisionRequest {
  action: "accept" | "override";
  decision?: "reverse" | "deny";
  amount_cents?: number;
  reason?: string;
}

export interface DecisionResponse {
  dispute_id: number;
  action: "accept" | "override";
  final_decision: "reverse" | "deny";
  final_amount_cents: number;
  claim_id: number;
}

async function asJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail));
  }
  return response.json() as Promise<T>;
}

export function listDisputes(): Promise<DisputeSummary[]> {
  return fetch(`${API_BASE}/disputes`).then((r) => asJson<DisputeSummary[]>(r));
}

export function getCase(disputeId: number): Promise<CaseDetail> {
  return fetch(`${API_BASE}/disputes/${disputeId}`).then((r) => asJson<CaseDetail>(r));
}

export function getClaim(claimId: number): Promise<ClaimView> {
  return fetch(`${API_BASE}/claims/${claimId}`).then((r) => asJson<ClaimView>(r));
}

export function decideCase(disputeId: number, body: DecisionRequest): Promise<DecisionResponse> {
  return fetch(`${API_BASE}/disputes/${disputeId}/decisions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => asJson<DecisionResponse>(r));
}

export function formatCents(cents: number | null): string {
  if (cents === null) return "—";
  return `$${(cents / 100).toFixed(2)}`;
}
