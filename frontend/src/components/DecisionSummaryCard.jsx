import "./DecisionSummaryCard.css";

const decisionColorMap = {
  APPROVE: "var(--color-approve)",
  DENY: "var(--color-deny)",
  NEEDS_MORE_INFO: "var(--color-needs-info)",
  APPROVE_WITH_BRIDGE: "var(--color-bridge)",
};

const decisionLabelMap = {
  APPROVE: "Approve",
  DENY: "Deny",
  NEEDS_MORE_INFO: "Needs More Info",
  APPROVE_WITH_BRIDGE: "Approve with Bridge",
};

const confidenceColorMap = {
  HIGH: "var(--color-high)",
  MEDIUM: "var(--color-medium)",
  LOW: "var(--color-low)",
};

function getScoreColor(score) {
  if (score > 70) return "var(--color-approve)";
  if (score >= 40) return "var(--color-needs-info)";
  return "var(--color-deny)";
}

function DecisionSummaryCard({ result }) {
  const { decision, equivalency_score, confidence } = result;
  const decisionColor = decisionColorMap[decision];
  const scoreColor = getScoreColor(equivalency_score);
  const confidenceColor = confidenceColorMap[confidence];

  return (
    <div
      className="decision-summary-card"
      style={{ borderLeftColor: decisionColor }}
    >
      <div className="decision-summary-card__header">
        <span
          className="decision-summary-card__decision-badge"
          style={{ backgroundColor: decisionColor }}
        >
          {decisionLabelMap[decision]}
        </span>
        <span
          className="decision-summary-card__confidence-badge"
          style={{ backgroundColor: confidenceColor }}
        >
          {confidence}
        </span>
      </div>

      <div className="decision-summary-card__score-section">
        <div className="decision-summary-card__score-label">
          Equivalency Score
        </div>
        <div className="decision-summary-card__score-value">
          <span
            className="decision-summary-card__score-number"
            style={{ color: scoreColor }}
          >
            {equivalency_score}
          </span>
          <span className="decision-summary-card__score-total">/100</span>
        </div>
        <div className="decision-summary-card__score-bar-track">
          <div
            className="decision-summary-card__score-bar-fill"
            style={{
              width: `${equivalency_score}%`,
              backgroundColor: scoreColor,
            }}
          />
        </div>
      </div>
    </div>
  );
}

export default DecisionSummaryCard;
