import { useState, useEffect, useRef } from "react";
import { useParams, Link } from "react-router-dom";
import { fetchCase, submitAdditionalInfo, fetchDecisionResult } from "../services/api";
import StatusBadge from "../components/StatusBadge";
import "./StudentCaseView.css";

export default function StudentCaseView() {
  const { studentId, id } = useParams();
  const [caseData, setCaseData] = useState(null);
  const [decisionResult, setDecisionResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showUploadForm, setShowUploadForm] = useState(false);
  const [uploadedExtra, setUploadedExtra] = useState(false);
  const [fileError, setFileError] = useState("");
  const fileInputRef = useRef(null);

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
      <div className="student-case-view">
        <p>Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="student-case-view">
        <p>Error: {error}. Is the backend running?</p>
        <Link to={`/student/${studentId}`}>Back to My Cases</Link>
      </div>
    );
  }

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

  const reviewerDecision = decisionResult?.latestReview?.reviewerDecision;
  const isApproved = caseData.status === "APPROVED" || (caseData.status === "REVIEWED" && reviewerDecision === "APPROVE");
  const isDenied = caseData.status === "DENIED" || (caseData.status === "REVIEWED" && reviewerDecision === "DENY");
  const needsMoreInfo = caseData.status === "NEEDS_INFO" || (caseData.status === "REVIEWED" && reviewerDecision === "NEEDS_MORE_INFO");

  return (
    <div className="student-case-view">
      <Link to={`/student/${studentId}`} className="student-case-view__back">
        &larr; Back to My Cases
      </Link>

      <div className="student-case-view__header">
        <div className="student-case-view__title-row">
          <h1 className="student-case-view__title">
            {caseData.id} &mdash; {caseData.courseRequested}
          </h1>
          <StatusBadge status={caseData.status} />
        </div>
        <p className="student-case-view__student-name">{caseData.studentName}</p>
      </div>

      <div className="student-case-view__documents">
        <h2 className="student-case-view__section-title">Uploaded Documents</h2>
        <ul className="student-case-view__doc-list">
          {caseData.documents.map((doc) => (
            <li className="student-case-view__doc-item" key={doc.id}>
              <span className="student-case-view__doc-name">{doc.name}</span>
              <span className="student-case-view__doc-date">
                {new Date(doc.uploadedAt).toLocaleDateString()}
              </span>
            </li>
          ))}
        </ul>
      </div>

      {(isApproved || isDenied) && (
        <div className={`student-case-view__decision-banner student-case-view__decision-banner--${isApproved ? "approve" : "deny"}`}>
          <h3 className="student-case-view__decision-title">
            {isApproved
              ? "Your request has been approved"
              : "Your request has been denied"}
          </h3>
          {decisionResult?.latestReview?.comment && (
            <p className="student-case-view__decision-comment">
              {decisionResult.latestReview.comment}
            </p>
          )}
        </div>
      )}

      {needsMoreInfo && !uploadedExtra && (
        <div className="student-case-view__decision-banner student-case-view__decision-banner--needs-more-info">
          <h3 className="student-case-view__decision-title">
            Additional Information Required
          </h3>
          {decisionResult?.latestReview?.comment && (
            <p className="student-case-view__decision-comment">
              {decisionResult.latestReview.comment}
            </p>
          )}
          {!showUploadForm ? (
            <button
              className="student-case-view__needs-info-btn"
              style={{ marginTop: "12px" }}
              onClick={() => setShowUploadForm(true)}
            >
              Upload Additional Documents
            </button>
          ) : (
            <div className="student-case-view__upload-form">
              <label className="student-case-view__upload-label">
                Select files to upload:
              </label>
              {fileError && (
                <div className="student-case-view__file-error">{fileError}</div>
              )}
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".pdf"
                className="student-case-view__upload-input"
                onChange={(e) => {
                  const files = e.target.files;
                  if (!files) return;
                  const invalid = Array.from(files).filter(
                    (f) => !f.name.toLowerCase().endsWith(".pdf")
                  );
                  if (invalid.length > 0) {
                    setFileError(`Only PDF files are allowed. Rejected: ${invalid.map((f) => f.name).join(", ")}`);
                    e.target.value = "";
                  } else {
                    setFileError("");
                  }
                }}
              />
              <div className="student-case-view__upload-actions">
                <button
                  className="student-case-view__upload-submit"
                  onClick={() => {
                    const files = Array.from(fileInputRef.current.files);
                    if (files.length === 0) return;
                    submitAdditionalInfo(id, files).then(() => {
                      return Promise.all([fetchCase(id), fetchDecisionResult(id)]);
                    }).then(([updated, updatedDecision]) => {
                      setCaseData(updated);
                      setDecisionResult(updatedDecision);
                      setUploadedExtra(true);
                    });
                  }}
                >
                  Upload & Submit
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
          Additional documents submitted successfully.
        </div>
      )}

    </div>
  );
}
