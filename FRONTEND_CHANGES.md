# Frontend Changes — What Changed and Why
**Branch:** firas-connecting-routes
**Date:** March 4, 2026

---

## 1. `frontend/vite.config.js`

**What changed:** Added a dev server proxy for `/api` requests pointing to `http://127.0.0.1:8001`.

**Why:** The frontend runs on port 5173 and the backend runs on port 8001. Without a proxy, the browser blocks cross-port fetch requests (CORS policy). The proxy makes every `/api/...` call from the frontend pass through Vite's dev server to the backend transparently, without needing any CORS configuration on the backend.

---

## 2. `frontend/src/services/api.js`

This file is the entire API layer — all backend communication goes through here. Four issues were fixed:

### 2a. `decisionPacket` → `evidencePacket`
**What changed:** In `mapCaseDetail`, changed `data.decisionPacket` to `data.evidencePacket`.
**Why:** Melissa renamed this field in PR #12 (`CaseDetailOut` schema). The old name returned `undefined`, so the evidence section of the reviewer case view was always empty.

### 2b. Status normalization — `.toUpperCase()`
**What changed:** In both `mapCaseOut` and `mapCaseDetail`, wrapped the status field with `(c.status || "").toUpperCase()`.
**Why:** The backend stores and returns statuses in lowercase (`ai_recommendation`, `needs_info`, `ready_for_decision`, `reviewed`, `uploaded`). All frontend components — `StatusBadge`, `ReviewerDashboard` filter logic, `ReviewerActionPanel` disable check — expect uppercase. Without this, no badge colors appeared, the filter tabs showed wrong counts, and the action panel was never disabled for reviewed cases.

### 2c. Added `assignedReviewerId` to `mapCaseOut`
**What changed:** Added `assignedReviewerId: c.assignedReviewerId || null` to the list mapping function.
**Why:** This field was added to the `CaseOut` schema in PR #12. It is needed by `ReviewerDashboard` to filter cases to only show the logged-in reviewer's own cases.

### 2d. Added `fetchReviewers()` function
**What changed:** Added a new exported function that calls `GET /api/reviewers`.
**Why:** The reviewer login flow needs to look up a reviewer by their UTC ID (`rev001`, etc.) and retrieve their database UUID. The UUID is what the backend uses to validate review submissions. This function enables that lookup at login time.

---

## 3. `frontend/src/services/auth.jsx`

**What changed:** `loginAsReviewer(utcId)` updated to `loginAsReviewer(utcId, reviewerId)`. The `reviewerId` (database UUID) is now stored in the auth context alongside the UTC ID string.

**Why:** The backend's `POST /api/cases/{id}/review` validates that the submitted `reviewerId` is a real UUID from the `reviewers` table. Previously, only the UTC ID string (e.g. `rev001`) was stored in auth context, and that string was being sent as `reviewerId` to the review endpoint — which always failed validation because `rev001` is not a UUID.

---

## 4. `frontend/src/pages/LoginPage.jsx`

**What changed:** The reviewer login path was rewritten from a simple navigation to an async lookup:
1. Calls `fetchReviewers()` to get all reviewers from the backend.
2. Finds the reviewer whose `utcId` matches what was typed.
3. If not found, shows an error: "Reviewer ID not found."
4. If found, calls `loginAsReviewer(utcId, match.reviewerId)` with both the UTC ID and the UUID.
5. Added a "Verifying..." loading state on the button during the API call.

**Why:** Required by the same UUID issue described in #3. The UUID is not known until the reviewer list is fetched. This also prevents anyone from logging in as a reviewer with a made-up ID.

---

## 5. `frontend/src/pages/ReviewerCaseReview.jsx`

### 5a. `user.utcId` → `user.reviewerId`
**What changed:** In `handleAction`, the fourth argument to `submitReviewerDecision` was changed from `user.utcId` to `user.reviewerId`.
**Why:** The review submission endpoint requires the reviewer's database UUID, not their UTC ID string. Same root cause as #3 and #4.

### 5b. Removed stray `console.log` from inside JSX
**What changed:** Removed the line `console.log("Decision Result:", decisionResult);` that was placed as a JSX child inside the `ai-decision-section` div.
**Why:** React renders unexpected non-JSX expressions inside `return ()` as literal text on screen. The string `console.log("Decision Result:", decisionResult);` was appearing visibly on the reviewer case page between the summary card and the explanation section.

---

## 6. `frontend/src/pages/ReviewerDashboard.jsx`

Three changes in this file:

### 6a. Added `useAuth` import and `user` context
**What changed:** Added `import { useAuth } from "../services/auth"` and `const { user } = useAuth()` inside the component.
**Why:** The dashboard had no access to the logged-in reviewer's identity. Without it, filtering by assigned reviewer was impossible.

### 6b. Filter cases by `assignedReviewerId`
**What changed:** After fetching all cases, filter to `!c.assignedReviewerId || c.assignedReviewerId === user.reviewerId` before setting state.
**Why:** `fetchAllCases()` returns all cases in the system. Without filtering, every reviewer saw every case regardless of who it was assigned to. The filter shows cases assigned to the logged-in reviewer, plus any unassigned cases (where `assignedReviewerId` is null) so no cases get hidden in edge cases.

### 6c. Added `READY_FOR_DECISION` to `PENDING_STATUSES`
**What changed:** Added `"READY_FOR_DECISION"` to the `PENDING_STATUSES` array used by the "Pending Review" filter tab.
**Why:** The array was `["REVIEW_PENDING", "AI_RECOMMENDATION"]`. The demo database has all cases in `READY_FOR_DECISION` status. Clicking "Pending Review" showed zero results because that status wasn't in the list.

---

## 7. `frontend/src/components/GapList.jsx`

**What changed:** Added null guards for `gap.severity` on two lines:
- CSS class: `gap-severity-badge--${gap.severity || "unknown"}`
- Display text: `gap.severity ? gap.severity.replace("_", " ") : "gap"`

**Why:** The backend's synthetic `NEEDS_MORE_INFO` result (produced by `validate_packet_or_raise` when evidence is missing) creates gap objects with only a `text` field — no `severity`. The real decision engine always includes `severity`, so this never surfaced in testing. When `gap.severity` is `undefined`, calling `.replace()` on it throws a TypeError and React unmounts the entire page, producing a white screen on any case with a NEEDS_MORE_INFO decision.

---

## Summary Table

| File | Change | Root Cause |
|---|---|---|
| `vite.config.js` | Added `/api` proxy to port 8001 | Browser CORS blocks cross-port requests |
| `services/api.js` | `evidencePacket` rename | Melissa's PR #12 schema rename |
| `services/api.js` | Status `.toUpperCase()` | Backend returns lowercase, frontend expects uppercase |
| `services/api.js` | `assignedReviewerId` in map | New field from PR #12, needed for reviewer filtering |
| `services/api.js` | `fetchReviewers()` added | Reviewer login needs UUID lookup |
| `services/auth.jsx` | Store `reviewerId` UUID | Review endpoint validates UUID, not UTC ID string |
| `LoginPage.jsx` | Async reviewer validation | Must fetch UUID at login before it can be stored |
| `ReviewerCaseReview.jsx` | Send `reviewerId` not `utcId` | Same UUID requirement on review submission |
| `ReviewerCaseReview.jsx` | Remove `console.log` from JSX | Was rendering as visible text on screen |
| `ReviewerDashboard.jsx` | Filter by `assignedReviewerId` | All reviewers were seeing all cases |
| `ReviewerDashboard.jsx` | Add `READY_FOR_DECISION` to pending | Pending filter tab was always empty |
| `GapList.jsx` | Null guard on `gap.severity` | Synthetic gaps have no severity → white screen crash |
