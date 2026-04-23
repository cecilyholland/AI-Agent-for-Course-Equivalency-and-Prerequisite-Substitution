import { useState, useEffect } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { fetchCourses } from "../services/api";
import "./StudentNewCase.css";

// ─── Course Picker Modal ─────────────────────────────────────────────────────

const PICKER_PAGE_SIZE = 8;

function CoursePickerModal({ onSelect, onClose }) {
  const [courses, setCourses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filterDept, setFilterDept] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    fetchCourses().then(setCourses).finally(() => setLoading(false));
  }, []);

  const filtered = courses.filter((c) => {
    const q = search.toLowerCase();
    if (q && !(c.courseCode || "").toLowerCase().includes(q) && !(c.displayName || "").toLowerCase().includes(q)) return false;
    if (filterDept && c.department !== filterDept) return false;
    return true;
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / PICKER_PAGE_SIZE));
  const paged = filtered.slice((page - 1) * PICKER_PAGE_SIZE, page * PICKER_PAGE_SIZE);
  const depts = [...new Set(courses.map((c) => c.department).filter(Boolean))].sort();

  return (
    <div className="course-picker-overlay" onClick={onClose}>
      <div className="course-picker-modal" onClick={(e) => e.stopPropagation()}>
        <div className="course-picker-header">
          <h3>Select Target Course</h3>
          <button className="course-picker-close" onClick={onClose}>&times;</button>
        </div>

        <div className="course-picker-filters">
          <input
            className="course-picker-search"
            type="text"
            placeholder="Search by code or name..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            autoFocus
          />
          <select
            className="course-picker-select"
            value={filterDept}
            onChange={(e) => { setFilterDept(e.target.value); setPage(1); }}
          >
            <option value="">All Departments</option>
            {depts.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>

        {loading ? (
          <p className="course-picker-empty">Loading courses...</p>
        ) : filtered.length === 0 ? (
          <p className="course-picker-empty">No courses match.</p>
        ) : (
          <>
            <table className="course-picker-table">
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Name</th>
                  <th>Credits</th>
                  <th>Department</th>
                </tr>
              </thead>
              <tbody>
                {paged.map((c) => (
                  <tr key={c.courseId} className="course-picker-row" onClick={() => onSelect(c)}>
                    <td><code>{c.courseCode}</code></td>
                    <td>{c.displayName}</td>
                    <td>{c.credits}</td>
                    <td>{c.department || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {totalPages > 1 && (
              <div className="course-picker-pagination">
                <button disabled={page === 1} onClick={() => setPage((p) => p - 1)}>‹</button>
                <span>{page} / {totalPages}</span>
                <button disabled={page === totalPages} onClick={() => setPage((p) => p + 1)}>›</button>
                <span className="course-picker-count">{filtered.length} courses</span>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default function StudentNewCase() {
  const navigate = useNavigate();
  const { studentId } = useParams();

  const [studentName, setStudentName] = useState("");
  const [targetCourse, setTargetCourse] = useState("");
  const [showPicker, setShowPicker] = useState(false);
  const [previousCourse, setPreviousCourse] = useState("");
  const [previousInstitution, setPreviousInstitution] = useState("");
  const [stagedFiles, setStagedFiles] = useState([]);
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
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
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("studentId", studentId);
      formData.append("studentName", studentName);
      formData.append("courseRequested", targetCourse);
      stagedFiles.forEach((f) => formData.append("files", f.file));

      const res = await fetch("/api/cases", {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error("Failed to create case");

      setSubmitted(true);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const canSubmit =
    studentName.trim() !== "" &&
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
            Your equivalency request has been submitted. Your documents
            are being processed and you will be notified of any updates.
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
                setStudentName("");
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
        <h2 className="new-case__section-title">Personal Information</h2>

        <label className="new-case__label" htmlFor="student-name">
          Full Name
        </label>
        <input
          id="student-name"
          className="new-case__input"
          type="text"
          placeholder="e.g. Jane Doe"
          value={studentName}
          onChange={(e) => setStudentName(e.target.value)}
        />
      </section>

      <section className="new-case__section">
        <h2 className="new-case__section-title">Course Information</h2>

        <label className="new-case__label">
          Target Course (at this university)
        </label>
        <button
          type="button"
          className="new-case__course-picker-btn"
          onClick={() => setShowPicker(true)}
        >
          {targetCourse || "Select a course..."}
        </button>
        {targetCourse && (
          <button
            type="button"
            className="new-case__course-clear"
            onClick={() => setTargetCourse("")}
          >
            &times; Clear
          </button>
        )}
        {showPicker && (
          <CoursePickerModal
            onSelect={(c) => { setTargetCourse(`${c.courseCode} - ${c.displayName}`); setShowPicker(false); }}
            onClose={() => setShowPicker(false)}
          />
        )}

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
          disabled={!canSubmit || loading}
          onClick={handleSubmit}
        >
          {loading ? "Submitting..." : "Submit Request"}
        </button>
        {!canSubmit && !loading && (
          <p className="new-case__submit-hint">
            Fill in all fields and upload at least one document to submit.
          </p>
        )}
      </div>
    </div>
  );
}