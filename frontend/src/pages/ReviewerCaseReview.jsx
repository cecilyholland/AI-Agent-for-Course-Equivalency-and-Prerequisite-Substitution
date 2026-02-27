import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { fetchCase, submitReviewerDecision, fetchDecisionResult } from "../services/api";
import { useAuth } from "../services/auth";
import StatusBadge from "../components/StatusBadge";
import DecisionSummaryCard from "../components/DecisionSummaryCard";
import DecisionExplanation from "../components/DecisionExplanation";
import ReviewerActionPanel from "../components/ReviewerActionPanel";
import AuditLogTimeline from "../components/AuditLogTimeline";
import "./ReviewerCaseReview.css";

export default function ReviewerCaseReview() {
  const { id } = useParams();
  const { user } = useAuth();
  const [caseData, setCaseData] = useState(null);
  const [decisionResult, setDecisionResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([fetchCase(id), fetchDecisionResult(id)])
      .then(([caseData, decisionData]) => {
        setCaseData(caseData);
        setDecisionResult(decisionData);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [id]);

  if (loading) {
    return (
      <div className="reviewer-case-review">
        <p>Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="reviewer-case-review">
        <p>Error: {error}. Is the backend running?</p>
        <Link to="/reviewer">Back to Dashboard</Link>
      </div>
    );
  }

  if (!caseData) {
    return (
      <div className="case-not-found">
        <p>Case not found.</p>
        <Link to="/reviewer">Back to Dashboard</Link>
      </div>
    );
  }

  const handleAction = async (action, comment) => {
    await submitReviewerDecision(id, action, comment, user.utcId);
    const [updated, updatedDecision] = await Promise.all([fetchCase(id), fetchDecisionResult(id)]);
    setCaseData(updated);
    setDecisionResult(updatedDecision);
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
            {caseData.id} &mdash; {caseData.courseRequested}
          </h1>
          <StatusBadge status={caseData.status} />
        </div>
        <div className="case-student-name">{caseData.studentName}</div>
      </div>

      <h2 className="section-title">Uploaded Documents</h2>
      <ul className="documents-list">
        {caseData.documents.map((doc) => (
          <li key={doc.id} className="document-item">
            <span className="document-name">{doc.name}</span>
            <span className="document-date">
              {formatDate(doc.uploadedAt)}
            </span>
          </li>
        ))}
      </ul>

      {decisionResult && (
        <div className="ai-decision-section">
          <h2 className="section-title">AI Recommendation</h2>
          <DecisionSummaryCard result={decisionResult} />
          <DecisionExplanation
            reasons={decisionResult.reasons}
            gaps={decisionResult.gaps}
            bridgePlan={decisionResult.bridgePlan}
            missingInfoRequests={decisionResult.missingInfoRequests}
          />
        </div>
      )}

      {caseData.reviewerComment && (
        <div className="existing-comment">
          <div className="existing-comment-label">Previous Reviewer Comment</div>
          <p>{caseData.reviewerComment}</p>
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
