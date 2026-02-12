import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { fetchCase, submitReviewerDecision } from "../services/api";
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
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchCase(id).then((data) => {
      setCaseData(data);
      setLoading(false);
    });
  }, [id]);

  if (!loading && !caseData) {
    return (
      <div className="case-not-found">
        <p>Case not found.</p>
        <Link to="/reviewer">Back to Dashboard</Link>
      </div>
    );
  }

  if (loading || !caseData) {
    return (
      <div className="reviewer-case-review">
        <p>Loading...</p>
      </div>
    );
  }

  const handleAction = async (action, comment) => {
    await submitReviewerDecision(id, action, comment, user.utcId);
    const updated = await fetchCase(id);
    setCaseData(updated);
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
