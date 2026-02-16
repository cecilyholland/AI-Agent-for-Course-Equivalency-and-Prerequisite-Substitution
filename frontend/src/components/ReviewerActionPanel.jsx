import { useState } from "react";
import "./ReviewerActionPanel.css";

const CONFIRMATION_MESSAGES = {
  APPROVE: "Thanks for sharing, this looks good. Approved.",
  DENY: "Case denied.",
  OVERRIDE: "Decision overridden by reviewer.",
};

export default function ReviewerActionPanel({
  caseId,
  currentStatus,
  onAction,
}) {
  const [selectedAction, setSelectedAction] = useState(null);
  const [comment, setComment] = useState("");
  const [confirmed, setConfirmed] = useState(false);

  const isDisabled = currentStatus === "REVIEWED" || confirmed;

  const handleActionClick = (action) => {
    if (isDisabled) return;
    setSelectedAction(action);
  };

  const handleConfirm = () => {
    if (!selectedAction) return;
    onAction(selectedAction, comment);
    setConfirmed(true);
  };

  return (
    <div className="reviewer-action-panel">
      <h3>Reviewer Action</h3>

      <div className="action-buttons-row">
        <button
          className={`action-btn action-btn--approve${
            selectedAction === "APPROVE" ? " action-btn--selected" : ""
          }`}
          disabled={isDisabled}
          onClick={() => handleActionClick("APPROVE")}
        >
          Approve
        </button>
        <button
          className={`action-btn action-btn--deny${
            selectedAction === "DENY" ? " action-btn--selected" : ""
          }`}
          disabled={isDisabled}
          onClick={() => handleActionClick("DENY")}
        >
          Deny
        </button>
        <button
          className={`action-btn action-btn--override${
            selectedAction === "OVERRIDE" ? " action-btn--selected" : ""
          }`}
          disabled={isDisabled}
          onClick={() => handleActionClick("OVERRIDE")}
        >
          Override
        </button>
      </div>

      <div className="comment-section">
        <label htmlFor={`comment-${caseId}`}>
          Reviewer Comment (optional)
        </label>
        <textarea
          id={`comment-${caseId}`}
          className="comment-textarea"
          placeholder="Add a comment about your decision..."
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          disabled={confirmed}
        />
      </div>

      {selectedAction && !confirmed && (
        <button className="confirm-btn" onClick={handleConfirm}>
          Confirm Decision
        </button>
      )}

      {confirmed && selectedAction && (
        <div className="confirmation-message">
          {CONFIRMATION_MESSAGES[selectedAction]}
        </div>
      )}
    </div>
  );
}
