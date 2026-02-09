// In-memory store -- swap this out for real DB calls later
import { mockCases } from "../mock/data.js";

// deep clone so we don't mutate the original mock data
let cases = JSON.parse(JSON.stringify(mockCases));

export function getAllCases() {
  return cases;
}

export function getCasesByStudent(studentId) {
  return cases.filter((c) => c.student_id === studentId);
}

export function getCaseById(caseId) {
  return cases.find((c) => c.id === caseId) || null;
}

export function updateCaseStatus(caseId, newStatus) {
  const c = cases.find((c) => c.id === caseId);
  if (c) c.status = newStatus;
}

export function addLogEntry(caseId, entry) {
  const c = cases.find((c) => c.id === caseId);
  if (c) c.logs.push(entry);
}

export function setReviewerComment(caseId, comment) {
  const c = cases.find((c) => c.id === caseId);
  if (c) c.reviewer_comment = comment;
}

export function addDocument(caseId, doc) {
  const c = cases.find((c) => c.id === caseId);
  if (c) c.documents.push(doc);
}

export function createCase(newCase) {
  cases.push(newCase);
}

// auto-increment: CASE-007, CASE-008, etc.
export function nextCaseId() {
  const maxNum = cases.reduce((max, c) => {
    const num = parseInt(c.id.replace("CASE-", ""), 10);
    return num > max ? num : max;
  }, 0);
  return `CASE-${String(maxNum + 1).padStart(3, "0")}`;
}

export function resetStore() {
  cases = JSON.parse(JSON.stringify(mockCases));
}
