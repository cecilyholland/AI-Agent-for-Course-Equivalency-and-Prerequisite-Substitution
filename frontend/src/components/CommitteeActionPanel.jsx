import { useState } from "react";
import "./ReviewerActionPanel.css";
import "./CommitteeActionPanel.css";

const CONFIRMATION_MESSAGES = {
  APPROVE: "Your vote to approve has been submitted.",
  APPROVE_WITH_BRIDGE: "Your vote to approve with bridge has been submitted.",
  DENY: "Your vote to deny has been submitted.",
  REQUEST_INFO: "Your vote to request more information has been submitted.",
};

export default function CommitteeActionPanel({ alreadyVoted, myVote, onVote }) {
  const [selectedAction, setSelectedAction] = useState(null);
  const [comment, setComment] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [commentError, setCommentError] = useState("");

  if (alreadyVoted && myVote) {
    return (
      <div className="committee-action-panel reviewer-action-panel">
        <h3>Your Vote</h3>
        <div className="committee-vote-readonly">
          <span className="committee-vote-action">{myVote.action.toUpperCase()}</span>
          {myVote.comment && (
            <p className="committee-vote-comment">{myVote.comment}</p>
          )}
        </div>
      </div>
    );
  }

  const handleActionClick = (action) => {
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
    onVote(selectedAction, comment);
    setConfirmed(true);
  };

  return (
    <div className="committee-action-panel reviewer-action-panel">
      <h3>Cast Your Vote</h3>

      <div className="action-buttons-row">
        <button
          className={`action-btn action-btn--approve${selectedAction === "APPROVE" ? " action-btn--selected" : ""}`}
          disabled={confirmed}
          onClick={() => handleActionClick("APPROVE")}
        >
          Approve
        </button>
        <button
          className={`action-btn action-btn--bridge${selectedAction === "APPROVE_WITH_BRIDGE" ? " action-btn--selected" : ""}`}
          disabled={confirmed}
          onClick={() => handleActionClick("APPROVE_WITH_BRIDGE")}
        >
          Approve with Bridge
        </button>
        <button
          className={`action-btn action-btn--deny${selectedAction === "DENY" ? " action-btn--selected" : ""}`}
          disabled={confirmed}
          onClick={() => handleActionClick("DENY")}
        >
          Deny
        </button>
        <button
          className={`action-btn action-btn--request-info${selectedAction === "REQUEST_INFO" ? " action-btn--selected" : ""}`}
          disabled={confirmed}
          onClick={() => handleActionClick("REQUEST_INFO")}
        >
          Request Info
        </button>
      </div>

      <div className="comment-section">
        <label>
          {(selectedAction === "REQUEST_INFO" || selectedAction === "APPROVE_WITH_BRIDGE")
            ? "Comment (required)"
            : "Comment (optional)"}
        </label>
        <textarea
          className="comment-textarea"
          placeholder={
            selectedAction === "REQUEST_INFO"
              ? "Describe what additional information is needed..."
              : selectedAction === "APPROVE_WITH_BRIDGE"
              ? "Describe the bridge requirements the student must fulfill..."
              : "Add a comment about your vote..."
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
          Confirm Vote
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
