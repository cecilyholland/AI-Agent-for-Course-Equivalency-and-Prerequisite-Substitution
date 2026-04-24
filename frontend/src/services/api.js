// API layer -- calls the FastAPI backend.

const API_BASE = "/api";

function mapCaseOut(c) {
  return {
    id: c.caseId,
    studentId: c.studentId,
    studentName: c.studentName,
    assignedReviewerId: c.assignedReviewerId || null,
    courseRequested: c.courseRequested,
    status: (c.status || "").toUpperCase(),
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

function buildLogs(auditLog) {
  const logs = [];
  (auditLog?.extractionRuns || []).forEach((r) => {
    logs.push({
      timestamp: r.createdAt,
      actor: "AGENT",
      action: "EXTRACTION",
      message: `Extraction run ${r.status}${r.errorMessage ? ": " + r.errorMessage : ""}`,
    });
  });
  (auditLog?.decisionRuns || []).forEach((r) => {
    logs.push({
      timestamp: r.createdAt,
      actor: "AGENT",
      action: "DECISION",
      message: `Decision run ${r.status}${r.errorMessage ? ": " + r.errorMessage : ""}`,
    });
  });
  (auditLog?.reviewActions || []).forEach((a) => {
    logs.push({
      timestamp: a.createdAt,
      actor: "REVIEWER",
      action: a.action.toUpperCase(),
      message: a.comment || `Reviewer action: ${a.action}`,
    });
  });
  return logs;
}

function mapCaseDetail(data) {
  const c = data.case;
  const reviewActions = data.auditLog?.reviewActions || [];
  const latestInfoRequest = [...reviewActions].reverse().find((a) => (a.action || "").toLowerCase() === "request_info");
  const latestDecision = [...reviewActions].reverse().find((a) => {
    const act = (a.action || "").toLowerCase();
    return act === "approve" || act === "deny" || act === "approve_with_bridge";
  });

  const resolveDecision = (action) => {
    if (action === "approve") return "APPROVED";
    if (action === "deny") return "DENIED";
    if (action === "approve_with_bridge") return "APPROVED WITH BRIDGE";
    return null;
  };

  let displayStatus = (c.status || "").toUpperCase();
  if ((displayStatus === "REVIEWED" || displayStatus === "COMMITTEE_DECIDED") && latestDecision) {
    displayStatus = resolveDecision(latestDecision.action) || displayStatus;
  }

  return {
    id: c.caseId,
    studentId: c.studentId,
    studentName: c.studentName,
    courseRequested: c.courseRequested,
    status: displayStatus,
    createdAt: c.createdAt,
    updatedAt: c.updatedAt,
    documents: (data.documents || []).map(mapDocument),
    evidencePacket: data.evidencePacket,
    logs: buildLogs(data.auditLog),
    reviewerComment: latestInfoRequest?.comment || null,
    reviewerDecision: latestDecision?.action || null,
    reviewerDecisionComment: latestDecision?.comment || null,
    decisionRuns: data.auditLog?.decisionRuns || [],
  };
}

// --- reads ---

export async function fetchStudentCases(studentId) {
  const res = await fetch(`${API_BASE}/cases?studentId=${studentId}`);
  if (!res.ok) throw new Error("Failed to fetch cases");
  const data = await res.json();

  const detailed = await Promise.all(
    data.map((c) => fetch(`${API_BASE}/cases/${c.caseId}`).then((r) => r.json()))
  );

  return detailed.map(mapCaseDetail);
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

// --- auth ---

export async function loginReviewer(utcId, password) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ utcId, password }),
  });
  if (res.status === 401) throw new Error("Invalid credentials");
  if (!res.ok) throw new Error("Login failed");
  return res.json(); // { reviewerId, reviewerName, utcId, role }
}

// --- reviewer lookup ---

export async function fetchReviewers() {
  const res = await fetch(`${API_BASE}/reviewers`);
  if (!res.ok) throw new Error("Failed to fetch reviewers");
  return res.json();
}

// --- reviewer actions ---

export async function submitReviewerDecision(caseId, action, comment, reviewerId) {
  const res = await fetch(`${API_BASE}/cases/${caseId}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, comment: comment || "", reviewerId }),
  });
  if (!res.ok) throw new Error("Failed to submit review");
  const data = await res.json();
  return mapCaseOut(data);
}

function mapDecisionResult(data) {
  const r = data.resultJson || {};
  return {
    decisionRunId: data.decisionRunId,
    createdAt: data.createdAt,
    needsMoreInfo: data.needsMoreInfo,
    missingFields: data.missingFields,
    decision: r.decision,
    equivalencyScore: r.equivalency_score,
    confidence: r.confidence,
    reasons: r.reasons || [],
    gaps: r.gaps || [],
    bridgePlan: r.bridge_plan || [],
    missingInfoRequests: r.missing_info_requests || [],
    latestReview: data.latestReview ? {
      reviewerDecision: data.latestReview.reviewerDecision,
      comment: data.latestReview.comment,
    } : null,
  };
}

export async function fetchDecisionResult(caseId) {
  const res = await fetch(`${API_BASE}/cases/${caseId}/decision/result/latest`);
  if (res.status === 404) return null; // no decision yet
  if (!res.ok) throw new Error("Failed to fetch decision result");
  const data = await res.json();
  return mapDecisionResult(data);
}

// --- admin: courses ---

export async function fetchCourses(department) {
  const url = department ? `${API_BASE}/courses?department=${encodeURIComponent(department)}` : `${API_BASE}/courses`;
  const res = await fetch(url);
  if (!res.ok) throw new Error("Failed to fetch courses");
  return res.json();
}

export async function addCourse({ courseCode, displayName, department, credits, labRequired, prerequisites, requiredTopics, requiredOutcomes, description }) {
  const res = await fetch(`${API_BASE}/courses`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ courseCode, displayName, department, credits, labRequired, prerequisites, requiredTopics, requiredOutcomes, description }),
  });
  if (!res.ok) throw new Error("Failed to add course");
  return res.json();
}

export async function deleteCourse(courseId) {
  const res = await fetch(`${API_BASE}/courses/${courseId}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete course");
}

export async function updateCourse(courseId, { displayName, department, credits, labRequired, prerequisites, requiredTopics, requiredOutcomes, description }) {
  const res = await fetch(`${API_BASE}/courses/${courseId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ displayName, department, credits, labRequired, prerequisites, requiredTopics, requiredOutcomes, description }),
  });
  if (!res.ok) throw new Error("Failed to update course");
  return res.json();
}

// --- admin: policy ---
// All fields are camelCase matching PolicyOut / PolicyUpdateIn

export async function fetchPolicy() {
  const res = await fetch(`${API_BASE}/policy`);
  if (!res.ok) throw new Error("Failed to fetch policy");
  return res.json();
}

export async function updatePolicy(policy) {
  const res = await fetch(`${API_BASE}/policy`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(policy),
  });
  if (!res.ok) throw new Error("Failed to update policy");
  return res.json();
}

// --- committee ---

export async function fetchCommitteeCases(reviewerId) {
  const res = await fetch(`${API_BASE}/cases?committeeReviewerId=${reviewerId}`);
  if (!res.ok) throw new Error("Failed to fetch committee cases");
  const data = await res.json();
  return data.map(mapCaseOut);
}

export async function fetchCommitteeInfo(caseId, reviewerId) {
  const res = await fetch(`${API_BASE}/cases/${caseId}/committee?reviewerId=${reviewerId}`);
  if (!res.ok) throw new Error("Failed to fetch committee info");
  return res.json();
}

export async function submitCommitteeVote(caseId, reviewerId, action, comment) {
  // Map frontend action names to backend expected values
  const actionMap = {
    APPROVE: "approve",
    DENY: "deny",
    REQUEST_INFO: "needs_more_info",
    NEEDS_MORE_INFO: "needs_more_info",
    APPROVE_WITH_BRIDGE: "approve_with_bridge",
  };
  const mappedAction = actionMap[action] || action.toLowerCase();
  const res = await fetch(`${API_BASE}/cases/${caseId}/committee/vote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reviewerId, action: mappedAction, comment: comment || "" }),
  });
  if (!res.ok) throw new Error("Failed to submit committee vote");
  const data = await res.json();
  return mapCaseOut(data);
}
