import { useState } from "react";
import "./ReviewerActionPanel.css";

const CONFIRMATION_MESSAGES = {
  APPROVE: "Thanks for sharing, this looks good. Approved.",
  APPROVE_WITH_BRIDGE: "Approved with bridge requirements. The student has been notified.",
  DENY: "Case denied.",
  REQUEST_INFO: "Request for additional information sent to the student.",
};

export default function ReviewerActionPanel({
  caseId,
  currentStatus,
  onAction,
}) {
  const [selectedAction, setSelectedAction] = useState(null);
  const [comment, setComment] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [commentError, setCommentError] = useState("");
  const isDisabled = currentStatus === "REVIEWED" || currentStatus === "APPROVED" || currentStatus === "APPROVED WITH BRIDGE" || currentStatus === "INVALID" || currentStatus === "DENIED" || currentStatus === "PENDING_COMMITTEE" || currentStatus === "COMMITTEE_DECIDED" || currentStatus === "NEEDS MORE INFO" || confirmed;

  const handleActionClick = (action) => {
    if (isDisabled) return;
    setSelectedAction(action);
    setCommentError("");
  };

  const handleConfirm = () => {
    if (!selectedAction) return;
    if ((selectedAction === "REQUEST_INFO" || selectedAction === "APPROVE_WITH_BRIDGE") && comment.trim() === "") {
      setCommentError(
        selectedAction === "APPROVE_WITH_BRIDGE"
          ? "Comment is required — describe the bridge requirements."
          : "Comment is required when requesting more info."
      );
      return;
    }
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
          className={`action-btn action-btn--bridge${
            selectedAction === "APPROVE_WITH_BRIDGE" ? " action-btn--selected" : ""
          }`}
          disabled={isDisabled}
          onClick={() => handleActionClick("APPROVE_WITH_BRIDGE")}
        >
          Approve with Bridge
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
          className={`action-btn action-btn--request-info${
            selectedAction === "REQUEST_INFO" ? " action-btn--selected" : ""
          }`}
          disabled={isDisabled}
          onClick={() => handleActionClick("REQUEST_INFO")}
        >
          Needs More Info
        </button>
      </div>

      <div className="comment-section">
        <label htmlFor={`comment-${caseId}`}>
          {(selectedAction === "REQUEST_INFO" || selectedAction === "APPROVE_WITH_BRIDGE")
            ? "Reviewer Comment (required)"
            : "Reviewer Comment (optional)"}
        </label>
        <textarea
          id={`comment-${caseId}`}
          className="comment-textarea"
          placeholder={
            selectedAction === "REQUEST_INFO"
              ? "Describe what additional information is needed..."
              : selectedAction === "APPROVE_WITH_BRIDGE"
              ? "Describe the bridge requirements the student must fulfill..."
              : "Add a comment about your decision..."
          }
          value={comment}
          onChange={(e) => {
            setComment(e.target.value);
            setCommentError("");
          }}
          disabled={confirmed}
        />
        {commentError && <p className="comment-error">{commentError}</p>}
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
