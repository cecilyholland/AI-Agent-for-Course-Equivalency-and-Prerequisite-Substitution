// API layer -- calls the FastAPI backend.

const API_BASE = "/api";

function mapCaseOut(c) {
  return {
    id: c.caseId,
    studentId: c.studentId,
    studentName: c.studentName,
    courseRequested: c.courseRequested,
    status: c.status,
    createdAt: c.createdAt,
    updatedAt: c.updatedAt,
  };
}

function mapDocument(d) {
  return {
    id: d.docId,
    name: d.filename,
    uploadedAt: d.createdAt,
  };
}

function mapCaseDetail(data) {
  const c = data.case;
  const reviewActions = data.auditLog?.reviewActions || [];
  const latestInfoRequest = [...reviewActions].reverse().find((a) => a.action === "request_info");

  return {
    id: c.caseId,
    studentId: c.studentId,
    studentName: c.studentName,
    courseRequested: c.courseRequested,
    status: c.status,
    createdAt: c.createdAt,
    updatedAt: c.updatedAt,
    documents: (data.documents || []).map(mapDocument),
    decisionPacket: data.decisionPacket,
    auditLog: data.auditLog,
    reviewerComment: latestInfoRequest?.comment || null,
  };
}

// --- reads ---

export async function fetchStudentCases(studentId) {
  const res = await fetch(`${API_BASE}/cases?studentId=${studentId}`);
  if (!res.ok) throw new Error("Failed to fetch cases");
  const data = await res.json();
  return data.map(mapCaseOut);
}

export async function fetchAllCases() {
  const res = await fetch(`${API_BASE}/cases`);
  if (!res.ok) throw new Error("Failed to fetch cases");
  const data = await res.json();
  return data.map(mapCaseOut);
}

export async function fetchCase(caseId) {
  const res = await fetch(`${API_BASE}/cases/${caseId}`);
  if (!res.ok) throw new Error("Failed to fetch case");
  const data = await res.json();
  return mapCaseDetail(data);
}

// --- student actions ---

export async function submitNewCase({ studentId, studentName, courseRequested, files }) {
  const form = new FormData();
  form.append("studentId", studentId);
  if (studentName) form.append("studentName", studentName);
  if (courseRequested) form.append("courseRequested", courseRequested);
  files.forEach((f) => form.append("files", f));
  const res = await fetch(`${API_BASE}/cases`, { method: "POST", body: form });
  if (!res.ok) throw new Error("Failed to create case");
  const data = await res.json();
  return mapCaseOut(data);
}

export async function submitAdditionalInfo(caseId, files) {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  const res = await fetch(`${API_BASE}/cases/${caseId}/documents`, { method: "POST", body: form });
  if (!res.ok) throw new Error("Failed to upload documents");
  const data = await res.json();
  return mapCaseOut(data);
}

// --- reviewer actions ---

export async function submitReviewerDecision(caseId, action, comment, reviewerId) {
  const res = await fetch(`${API_BASE}/cases/${caseId}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, comment, reviewerId }),
  });
  if (!res.ok) throw new Error("Failed to submit review");
  const data = await res.json();
  return mapCaseOut(data);
}
