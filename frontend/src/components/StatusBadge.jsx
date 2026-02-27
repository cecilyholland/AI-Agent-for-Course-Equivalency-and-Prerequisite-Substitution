import "./StatusBadge.css";

const statusColorMap = {
  UPLOADED: "var(--color-uploaded)",
  EXTRACTING: "var(--color-extracting)",
  READY_FOR_DECISION: "var(--color-ready)",
  AI_RECOMMENDATION: "var(--color-decided)",
  NEEDS_INFO: "var(--color-needs-info)",
  REVIEW_PENDING: "var(--color-pending)",
  REVIEWED: "var(--color-reviewed)",
  APPROVED: "var(--color-approve)",
  DENIED: "var(--color-deny)",
};

function StatusBadge({ status }) {
  const label = status.replace(/_/g, " ");
  const color = statusColorMap[status];

  return (
    <span
      className="status-badge"
      style={{ backgroundColor: color }}
    >
      {label}
    </span>
  );
}

export default StatusBadge;
