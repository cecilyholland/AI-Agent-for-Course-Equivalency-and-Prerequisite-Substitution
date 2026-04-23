import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { fetchCase, fetchDecisionResult, fetchCommitteeInfo, submitCommitteeVote } from "../services/api";
import { useAuth } from "../services/auth";
import StatusBadge from "../components/StatusBadge";
import DecisionSummaryCard from "../components/DecisionSummaryCard";
import DecisionExplanation from "../components/DecisionExplanation";
import CommitteeActionPanel from "../components/CommitteeActionPanel";
import "./ReviewerCaseReview.css";
import "./CommitteeCaseReview.css";

export default function CommitteeCaseReview() {
  const { id } = useParams();
  const { user } = useAuth();
  const [caseData, setCaseData] = useState(null);
  const [decisionResult, setDecisionResult] = useState(null);
  const [committeeInfo, setCommitteeInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([
      fetchCase(id),
      fetchDecisionResult(id),
      fetchCommitteeInfo(id, user.reviewerId),
    ])
      .then(([caseRes, decisionRes, committeeRes]) => {
        setCaseData(caseRes);
        setDecisionResult(decisionRes);
        setCommitteeInfo(committeeRes);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [id]);

  const handleVote = async (action, comment) => {
    try {
      await submitCommitteeVote(id, user.reviewerId, action, comment);
      const updated = await fetchCommitteeInfo(id, user.reviewerId);
      setCommitteeInfo(updated);
    } catch (err) {
      setError(err.message);
    }
  };

  const formatDate = (dateStr) =>
    new Date(dateStr).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });

  if (loading) {
    return <div className="reviewer-case-review"><p>Loading...</p></div>;
  }

  if (error) {
    return (
      <div className="reviewer-case-review">
        <p>Error: {error}. Is the backend running?</p>
        <Link to="/reviewer/committee">Back to Committee Cases</Link>
      </div>
    );
  }

  if (!caseData) {
    return (
      <div className="case-not-found">
        <p>Case not found.</p>
        <Link to="/reviewer/committee">Back to Committee Cases</Link>
      </div>
    );
  }

  return (
    <div className="reviewer-case-review">
      <Link to="/reviewer/committee" className="back-link">
        &larr; Back to Committee Cases
      </Link>

      <div className="case-header">
        <div className="case-header-title">
          <h1>{caseData.id} &mdash; {caseData.courseRequested}</h1>
          <StatusBadge status={caseData.status} />
        </div>
        <div className="case-student-name">{caseData.studentName}</div>
      </div>

      {(caseData.reviewerDecision || caseData.reviewerDecisionComment) && (
        <div className="existing-comment">
          <div className="existing-comment-label">Reviewer Decision</div>
          {caseData.reviewerDecision && (
            <span className="reviewer-decision-badge">
              {caseData.reviewerDecision.replace(/_/g, " ").toUpperCase()}
            </span>
          )}
          {caseData.reviewerDecisionComment && (
            <p style={{ marginTop: "8px" }}>{caseData.reviewerDecisionComment}</p>
          )}
        </div>
      )}

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

      {committeeInfo && committeeInfo.members?.length > 0 && (
        <div className="committee-members-section">
          <h2 className="section-title">Committee Members</h2>
          <ul className="committee-members-list">
            {committeeInfo.members.map((m) => (
              <li key={m.reviewerId} className="committee-member-item">
                <span className="committee-member-name">{m.reviewerName}</span>
                <span className={`committee-vote-badge${m.hasVoted ? " committee-vote-badge--voted" : " committee-vote-badge--pending"}`}>
                  {m.hasVoted ? "Voted" : "Pending"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="action-panel-section">
        <h2 className="section-title">Your Vote</h2>
        <CommitteeActionPanel
          alreadyVoted={!!committeeInfo?.myVote}
          myVote={committeeInfo?.myVote}
          onVote={handleVote}
        />
      </div>
    </div>
  );
}
