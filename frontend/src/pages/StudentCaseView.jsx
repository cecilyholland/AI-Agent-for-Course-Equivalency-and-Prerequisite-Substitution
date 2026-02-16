import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { fetchCase, submitAdditionalInfo } from "../services/api";
import StatusBadge from "../components/StatusBadge";
import DecisionSummaryCard from "../components/DecisionSummaryCard";
import DecisionExplanation from "../components/DecisionExplanation";
import AuditLogTimeline from "../components/AuditLogTimeline";
import "./StudentCaseView.css";

export default function StudentCaseView() {
  const { studentId, id } = useParams();
  const [showUploadForm, setShowUploadForm] = useState(false);
  const [uploadedExtra, setUploadedExtra] = useState(false);
  const [, forceUpdate] = useState(0);

  const caseData = fetchCase(id);

  if (!caseData) {
    return (
      <div className="student-case-view">
        <div className="student-case-view__not-found">
          <h2>Case not found</h2>
          <p>No case exists with ID &ldquo;{id}&rdquo;.</p>
          <Link to={`/student/${studentId}`}>Back to My Cases</Link>
        </div>
      </div>
    );
  }

  const { decision_result } = caseData;
  const showNeedsInfoAlert =
    caseData.status === "NEEDS_INFO" &&
    decision_result?.missing_info_requests &&
    decision_result.missing_info_requests.length > 0;

  return (
    <div className="student-case-view">
      <Link to={`/student/${studentId}`} className="student-case-view__back">
        &larr; Back to My Cases
      </Link>

      <div className="student-case-view__header">
        <div className="student-case-view__title-row">
          <h1 className="student-case-view__title">
            {caseData.id} &mdash; {caseData.course_requested}
          </h1>
          <StatusBadge status={caseData.status} />
        </div>
        <p className="student-case-view__student-name">{caseData.student_name}</p>
      </div>

      <div className="student-case-view__documents">
        <h2 className="student-case-view__section-title">Uploaded Documents</h2>
        <ul className="student-case-view__doc-list">
          {caseData.documents.map((doc) => (
            <li className="student-case-view__doc-item" key={doc.id}>
              <span className="student-case-view__doc-name">{doc.name}</span>
              <span className="student-case-view__doc-date">
                {new Date(doc.uploaded_at).toLocaleDateString()}
              </span>
            </li>
          ))}
        </ul>
      </div>

      {decision_result && (
        <div className="student-case-view__recommendation">
          <h2 className="student-case-view__section-title">AI Recommendation</h2>
          <DecisionSummaryCard result={decision_result} />
          <DecisionExplanation
            reasons={decision_result.reasons}
            gaps={decision_result.gaps}
            bridgePlan={decision_result.bridge_plan}
            missingInfoRequests={decision_result.missing_info_requests}
          />
        </div>
      )}

      {showNeedsInfoAlert && !uploadedExtra && (
        <div className="student-case-view__needs-info-alert">
          <h3 className="student-case-view__needs-info-title">
            Additional Information Required
          </h3>
          <ul className="student-case-view__needs-info-list">
            {decision_result.missing_info_requests.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>

          {!showUploadForm ? (
            <button
              className="student-case-view__needs-info-btn"
              onClick={() => setShowUploadForm(true)}
            >
              Submit Additional Info
            </button>
          ) : (
            <div className="student-case-view__upload-form">
              <label className="student-case-view__upload-label">
                Select files to upload:
              </label>
              <input
                type="file"
                multiple
                accept=".pdf,.doc,.docx,.png,.jpg,.jpeg"
                className="student-case-view__upload-input"
              />
              <div className="student-case-view__upload-actions">
                <button
                  className="student-case-view__upload-submit"
                  onClick={() => {
                    submitAdditionalInfo(id, [{ name: "Additional_Document.pdf" }]);
                    setUploadedExtra(true);
                    forceUpdate((n) => n + 1);
                  }}
                >
                  Upload &amp; Submit
                </button>
                <button
                  className="student-case-view__upload-cancel"
                  onClick={() => setShowUploadForm(false)}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {uploadedExtra && (
        <div className="student-case-view__upload-success">
          Additional documents submitted. The AI agent will re-evaluate your
          case shortly.
        </div>
      )}

      <div className="student-case-view__audit-log">
        <AuditLogTimeline logs={caseData.logs} />
      </div>
    </div>
  );
}
