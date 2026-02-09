import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { fetchCase, submitReviewerDecision } from "../services/api";
import StatusBadge from "../components/StatusBadge";
import DecisionSummaryCard from "../components/DecisionSummaryCard";
import DecisionExplanation from "../components/DecisionExplanation";
import ReviewerActionPanel from "../components/ReviewerActionPanel";
import AuditLogTimeline from "../components/AuditLogTimeline";
import "./ReviewerCaseReview.css";

export default function ReviewerCaseReview() {
  const { id } = useParams();
  const [, forceUpdate] = useState(0);

  const caseData = fetchCase(id);

  if (!caseData) {
    return (
      <div className="case-not-found">
        <p>Case not found.</p>
        <Link to="/reviewer">Back to Dashboard</Link>
      </div>
    );
  }

  const handleAction = (action, comment) => {
    submitReviewerDecision(id, action, comment);
    forceUpdate((n) => n + 1);
  };

  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className="reviewer-case-review">
      <Link to="/reviewer" className="back-link">
        &larr; Back to Dashboard
      </Link>

      <div className="case-header">
        <div className="case-header-title">
          <h1>
            {caseData.id} &mdash; {caseData.course_requested}
          </h1>
          <StatusBadge status={caseData.status} />
        </div>
        <div className="case-student-name">{caseData.student_name}</div>
      </div>

      <h2 className="section-title">Uploaded Documents</h2>
      <ul className="documents-list">
        {caseData.documents.map((doc) => (
          <li key={doc.id} className="document-item">
            <span className="document-name">{doc.name}</span>
            <span className="document-date">
              {formatDate(doc.uploaded_at)}
            </span>
          </li>
        ))}
      </ul>

      {caseData.decision_result && (
        <div className="ai-recommendation-panel">
          <h2 className="section-title">AI Recommendation</h2>
          <DecisionSummaryCard result={caseData.decision_result} />
          <DecisionExplanation
            reasons={caseData.decision_result.reasons}
            gaps={caseData.decision_result.gaps}
            bridgePlan={caseData.decision_result.bridge_plan}
            missingInfoRequests={caseData.decision_result.missing_info_requests}
          />
        </div>
      )}

      {caseData.reviewer_comment && (
        <div className="existing-comment">
          <div className="existing-comment-label">Previous Reviewer Comment</div>
          <p>{caseData.reviewer_comment}</p>
        </div>
      )}

      <div className="action-panel-section">
        <h2 className="section-title">Take Action</h2>
        <ReviewerActionPanel
          caseId={caseData.id}
          currentStatus={caseData.status}
          onAction={handleAction}
        />
      </div>

      <div className="audit-log-section">
        <h2 className="section-title">Audit Log</h2>
        <AuditLogTimeline logs={caseData.logs} />
      </div>
    </div>
  );
}
