const REASON_LABELS: Record<string, string> = {
  DUP: "Duplicate",
  BIL: "Billing",
  DOC: "Documents",
  COV: "Coverage",
};

export function ReasonBadge({ reasonCode }: { reasonCode: string }) {
  const className = `badge badge-${reasonCode.toLowerCase()}`;
  return <span className={className}>{REASON_LABELS[reasonCode] ?? reasonCode}</span>;
}

export function GateActionBadge({ action }: { action: "auto_resolve" | "escalate" | null }) {
  if (action === "auto_resolve") {
    return (
      <span className="badge badge-success">
        <span className="dot" /> Auto-resolve
      </span>
    );
  }
  if (action === "escalate") {
    return (
      <span className="badge badge-warning">
        <span className="dot" /> Escalate
      </span>
    );
  }
  return <span className="badge badge-neutral">No recommendation</span>;
}
