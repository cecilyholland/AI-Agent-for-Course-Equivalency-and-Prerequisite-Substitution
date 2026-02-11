import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { fetchCase, submitAdditionalInfo } from "../services/api";
import StatusBadge from "../components/StatusBadge";
import "./StudentCaseView.css";

export default function StudentCaseView() {
  const { studentId, id } = useParams();
  const [showUploadForm, setShowUploadForm] = useState(false);
  const [uploadedExtra, setUploadedExtra] = useState(false);
  const [fileError, setFileError] = useState("");
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

      {caseData.status === "NEEDS_INFO" && !uploadedExtra && (
        <div className="student-case-view__needs-info-alert">
          <h3 className="student-case-view__needs-info-title">
            Additional Information Required
          </h3>

          {caseData.reviewer_comment && (
            <div className="student-case-view__reviewer-comment">
              <span className="student-case-view__reviewer-comment-label">Reviewer Comment</span>
              <p className="student-case-view__reviewer-comment-text">{caseData.reviewer_comment}</p>
            </div>
          )}

          {!showUploadForm ? (
            <button
              className="student-case-view__needs-info-btn"
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
                    submitAdditionalInfo(id, [{ name: "Additional_Document.pdf" }]);
                    setUploadedExtra(true);
                    forceUpdate((n) => n + 1);
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
