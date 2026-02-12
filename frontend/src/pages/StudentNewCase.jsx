import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { submitNewCase } from "../services/api";
import "./StudentNewCase.css";

export default function StudentNewCase() {
  const navigate = useNavigate();
  const { studentId } = useParams();

  const [targetCourse, setTargetCourse] = useState("");
  const [previousCourse, setPreviousCourse] = useState("");
  const [previousInstitution, setPreviousInstitution] = useState("");
  const [stagedFiles, setStagedFiles] = useState([]);
  const [submitted, setSubmitted] = useState(false);
  const [fileError, setFileError] = useState("");

  const formatSize = (bytes) => {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  };

  const validateAndAddFiles = (fileList) => {
    const valid = [];
    const invalid = [];
    Array.from(fileList).forEach((f) => {
      if (f.name.toLowerCase().endsWith(".pdf")) {
        valid.push({ file: f, name: f.name, size: formatSize(f.size) });
      } else {
        invalid.push(f.name);
      }
    });
    if (invalid.length > 0) {
      setFileError(`Only PDF files are allowed. Rejected: ${invalid.join(", ")}`);
    } else {
      setFileError("");
    }
    return valid;
  };

  const handleFileSelect = (e) => {
    const files = e.target.files;
    if (!files) return;
    const valid = validateAndAddFiles(files);
    setStagedFiles((prev) => [...prev, ...valid]);
    e.target.value = "";
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const files = e.dataTransfer.files;
    const valid = validateAndAddFiles(files);
    setStagedFiles((prev) => [...prev, ...valid]);
  };

  const removeFile = (index) => {
    setStagedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async () => {
    try {
      await submitNewCase({
        studentId,
        studentName: studentId,
        courseRequested: targetCourse,
        files: stagedFiles.map((f) => f.file),
      });
      setSubmitted(true);
    } catch (err) {
      console.error(err);
    }
  };

  const canSubmit =
    targetCourse.trim() !== "" &&
    previousCourse.trim() !== "" &&
    previousInstitution.trim() !== "" &&
    stagedFiles.length > 0;

  if (submitted) {
    return (
      <div className="new-case">
        <div className="new-case__success">
          <div className="new-case__success-icon">&#x2705;</div>
          <h2>Request Submitted</h2>
          <p>
            Your equivalency request has been submitted. The AI agent will begin
            extracting and analyzing your documents shortly.
          </p>
          <p className="new-case__success-status">
            Status: <strong>UPLOADED</strong>
          </p>
          <div className="new-case__success-actions">
            <Link to={`/student/${studentId}`} className="new-case__btn new-case__btn--primary">
              Back to My Cases
            </Link>
            <button
              className="new-case__btn new-case__btn--secondary"
              onClick={() => {
                setSubmitted(false);
                setTargetCourse("");
                setPreviousCourse("");
                setPreviousInstitution("");
                setStagedFiles([]);
              }}
            >
              Submit Another
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="new-case">
      <Link to={`/student/${studentId}`} className="new-case__back">
        &larr; Back to My Cases
      </Link>

      <h1 className="new-case__title">New Equivalency Request</h1>
      <p className="new-case__subtitle">
        Submit your course documents for AI-powered equivalency evaluation.
      </p>

      <section className="new-case__section">
        <h2 className="new-case__section-title">Course Information</h2>

        <label className="new-case__label" htmlFor="target-course">
          Target Course (at this university)
        </label>
        <select
          id="target-course"
          className="new-case__select"
          value={targetCourse}
          onChange={(e) => setTargetCourse(e.target.value)}
        >
          <option value="">Select a course...</option>
          <option value="CPSC 2100 - Intro to Programming">
            CPSC 2100 - Intro to Programming
          </option>
          <option value="CPSC 3400 - Data Structures">
            CPSC 3400 - Data Structures
          </option>
          <option value="CPSC 3600 - Computer Networks">
            CPSC 3600 - Computer Networks
          </option>
          <option value="CPSC 4100 - Algorithms">
            CPSC 4100 - Algorithms
          </option>
          <option value="CPSC 4500 - Operating Systems">
            CPSC 4500 - Operating Systems
          </option>
          <option value="CPSC 4600 - Database Systems">
            CPSC 4600 - Database Systems
          </option>
        </select>

        <label className="new-case__label" htmlFor="prev-course">
          Previous Course Name
        </label>
        <input
          id="prev-course"
          className="new-case__input"
          type="text"
          placeholder="e.g. CS 301 - Data Structures and Algorithms"
          value={previousCourse}
          onChange={(e) => setPreviousCourse(e.target.value)}
        />

        <label className="new-case__label" htmlFor="prev-institution">
          Previous Institution
        </label>
        <input
          id="prev-institution"
          className="new-case__input"
          type="text"
          placeholder="e.g. University of Tennessee, Chattanooga"
          value={previousInstitution}
          onChange={(e) => setPreviousInstitution(e.target.value)}
        />
      </section>

      <section className="new-case__section">
        <h2 className="new-case__section-title">Upload Documents</h2>
        <p className="new-case__section-desc">
          Upload your transcript, course syllabus, and any supporting documents
          (PDF files only).
        </p>

        {fileError && (
          <div className="new-case__file-error">{fileError}</div>
        )}

        <div
          className="new-case__dropzone"
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
        >
          <div className="new-case__dropzone-content">
            <span className="new-case__dropzone-icon">&#x1F4C4;</span>
            <p>Drag and drop files here</p>
            <p className="new-case__dropzone-or">or</p>
            <label className="new-case__browse-btn">
              Browse Files
              <input
                type="file"
                multiple
                accept=".pdf"
                onChange={handleFileSelect}
                hidden
              />
            </label>
          </div>
        </div>

        {stagedFiles.length > 0 && (
          <div className="new-case__file-list">
            <h4>Staged Files ({stagedFiles.length})</h4>
            {stagedFiles.map((f, i) => (
              <div key={i} className="new-case__file-item">
                <div className="new-case__file-info">
                  <span className="new-case__file-name">{f.name}</span>
                  <span className="new-case__file-size">{f.size}</span>
                </div>
                <button
                  className="new-case__file-remove"
                  onClick={() => removeFile(i)}
                  title="Remove file"
                >
                  &times;
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      <div className="new-case__submit-area">
        <button
          className="new-case__btn new-case__btn--primary new-case__btn--lg"
          disabled={!canSubmit}
          onClick={handleSubmit}
        >
          Submit Request
        </button>
        {!canSubmit && (
          <p className="new-case__submit-hint">
            Fill in all fields and upload at least one document to submit.
          </p>
        )}
      </div>
    </div>
  );
}
