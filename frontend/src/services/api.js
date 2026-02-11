// API layer -- currently hits the in-memory store.
// Swap function bodies with fetch() calls when the backend is ready.
import {
  getAllCases,
  getCasesByStudent,
  getCaseById,
  updateCaseStatus,
  addLogEntry,
  setReviewerComment,
  addDocument,
  createCase,
  nextCaseId,
} from "./store.js";

// --- reads ---

export function fetchStudentCases(studentId) {
  return getCasesByStudent(studentId);
}

export function fetchAllCases() {
  return getAllCases();
}

export function fetchCase(caseId) {
  return getCaseById(caseId);
}

// --- student actions ---

export function submitNewCase({ studentId, studentName, courseRequested, files }) {
  const now = new Date().toISOString();
  const caseId = nextCaseId();

  const documents = files.map((f, i) => ({
    id: `doc-${caseId}-${i}`,
    name: f.name,
    uploaded_at: now,
  }));

  const newCase = {
    id: caseId,
    student_id: studentId,
    student_name: studentName,
    course_requested: courseRequested,
    status: "UPLOADED",
    documents,
    logs: [
      {
        timestamp: now,
        actor: "STUDENT",
        action: "UPLOAD",
        message: `Uploaded ${files.length} document(s) for ${courseRequested} equivalency request.`,
      },
    ],
  };

  createCase(newCase);
  return newCase;
}

export function submitAdditionalInfo(caseId, files) {
  const now = new Date().toISOString();

  files.forEach((f, i) => {
    addDocument(caseId, {
      id: `doc-${caseId}-extra-${i}`,
      name: f.name,
      uploaded_at: now,
    });
  });

  addLogEntry(caseId, {
    timestamp: now,
    actor: "STUDENT",
    action: "UPLOAD",
    message: `Submitted ${files.length} additional document(s).`,
  });

  // backend would re-run extraction; for now just flip status
  updateCaseStatus(caseId, "EXTRACTING");

  addLogEntry(caseId, {
    timestamp: new Date(Date.now() + 1).toISOString(),
    actor: "AGENT",
    action: "STATUS_CHANGE",
    message: "Case status changed to EXTRACTING. Re-evaluating with new documents.",
  });

  return getCaseById(caseId);
}

// --- reviewer actions ---

export function submitReviewerDecision(caseId, action, comment) {
  const now = new Date().toISOString();
  const isRequestInfo = action === "REQUEST_INFO";

  addLogEntry(caseId, {
    timestamp: now,
    actor: "REVIEWER",
    action: action.toUpperCase(),
    message: isRequestInfo
      ? `Reviewer requested additional information. Comment: ${comment}`
      : comment
        ? `Reviewer ${action.toLowerCase()}d. Comment: ${comment}`
        : `Reviewer ${action.toLowerCase()}d.`,
  });

  if (comment) {
    setReviewerComment(caseId, comment);
  }

  const newStatus = isRequestInfo ? "NEEDS_INFO" : "REVIEWED";
  updateCaseStatus(caseId, newStatus);

  addLogEntry(caseId, {
    timestamp: new Date(Date.now() + 1).toISOString(),
    actor: "AGENT",
    action: "STATUS_CHANGE",
    message: isRequestInfo
      ? "Case status changed to NEEDS_INFO."
      : "Case status changed to REVIEWED.",
  });

  return getCaseById(caseId);
}
