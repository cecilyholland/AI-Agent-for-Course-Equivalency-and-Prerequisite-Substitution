# Frontend-Backend Integration — Setup Notes
**Date:** March 4, 2026
**Branch:** firas-connecting-routes

---

## Overview

This document walks through everything done to connect the frontend to the live backend, the issues encountered along the way, and what still needs team discussion before the next step.

---

## 1. Pulled Latest Changes from GitHub

Merged PRs #15, #16, #17, and #18 from `main` into `firas-connecting-routes`.

**What came in:**
- **PR #15 (Cecily)** — Full OCR extraction pipeline for large PDFs. Smart page selection (12–31 pages instead of 975+). Added 10 real student test cases (Brown, Georgia Tech, MIT). No frontend impact.
- **PR #16 (Melissa)** — Major backend update: `GET /api/cases` list endpoint restored (was removed in PR #12), extraction and decision engine now auto-trigger together via `POST /api/cases/{id}/extraction/start`, `GET /api/reviewers` endpoint added, prepopulated demo database (`ai_db_demo_prepopulated.dump`) with 10 cases.
- **PR #17 (Colby)** — Added reviewer access logs and agent fail logs to `main.py`. No frontend impact.
- **PR #18 (Melissa)** — Bug fix: `GET /api/reviewers` was returning an error due to wrong attribute name (`r.utcId` instead of `r.utc_id`). Now correctly returns `utcId` per reviewer.

---

## 2. Frontend Fixes Committed

Four files were updated to match the current backend contract.

### `frontend/src/services/api.js`
| Fix | Reason |
|---|---|
| `data.decisionPacket` → `data.evidencePacket` | Melissa renamed this field in `CaseDetailOut` (PR #12). The old name returned `undefined`, breaking the evidence display. |
| Status normalization: `(c.status).toUpperCase()` | Backend stores and returns statuses in **lowercase** (`ai_recommendation`, `needs_info`, `uploaded`). `StatusBadge` expects **uppercase**. Without this, no badge colors showed and the REVIEWED→APPROVED/DENIED logic never triggered. |
| Added `assignedReviewerId` to `mapCaseOut` | New field added to `CaseOut` schema in PR #12. |
| Added `fetchReviewers()` function | Calls `GET /api/reviewers` to support reviewer login validation. |

### `frontend/src/services/auth.jsx`
`loginAsReviewer(utcId)` updated to `loginAsReviewer(utcId, reviewerId)`.
**Reason:** The backend's `POST /api/cases/{id}/review` validates that `reviewerId` is a real UUID from the `reviewers` table. Previously we were sending the UTC ID string (e.g. `rev001`) which is not a UUID and failed backend validation.

### `frontend/src/pages/LoginPage.jsx`
Reviewer login now calls `GET /api/reviewers`, finds the reviewer matching the entered UTC ID, and stores their database UUID.
**Reason:** Same as above — the UUID is needed to submit reviewer actions. Also added a "Verifying..." loading state on the login button and an error message if the ID isn't found.

### `frontend/src/pages/ReviewerCaseReview.jsx`
`user.utcId` → `user.reviewerId` when submitting a review action.
**Reason:** The review submission now correctly sends the reviewer's database UUID.

---

## 3. Backend Environment Setup

### `.env` file (created at project root)
```
UPLOAD_DIR=Data/Uploads
DATABASE_URL=postgresql+psycopg2://postgres:ai_db_demo@localhost:8000/ai_db_demo
```
**Note:** `main.py` reads `DATABASE_URL` directly from `os.environ` — it does NOT auto-load `.env`. Must use `dotenv run --` when starting the server (see Step 5).

### Python dependencies installed into venv
```bash
pip install psycopg2-binary   # PostgreSQL driver (not in venv by default)
pip install python-dotenv     # Needed for dotenv run -- command
pip install httpx             # Missing from venv, imported by main.py
```

---

## 4. PostgreSQL Setup

### Issue: PostgreSQL running on port 8000, not 5432
On this machine, PostgreSQL 18 is configured to use **port 8000** instead of the default 5432. This caused all initial connection attempts to fail silently.
**Fix:** Updated `.env` to use port 8000 in the connection string.
**How to verify:** `cat "C:/Program Files/PostgreSQL/18/data/postgresql.conf" | grep port`

### Restoring Melissa's prepopulated database
```bash
createdb -U postgres -p 8000 ai_db_demo
pg_restore -U postgres -p 8000 -d ai_db_demo --clean --if-exists Database/ai_db_demo_prepopulated.dump
```

**Issue encountered:** 21 `role "melissastan" does not exist` errors during restore.
**What this means:** The dump was created on Melissa's machine where her PostgreSQL username is `melissastan`. On other machines that user doesn't exist, so ownership assignment fails.
**Impact:** None — the actual table data, schema, and indexes all restored correctly. Tables are owned by `postgres` on each local machine instead. Verified with:
```sql
SELECT COUNT(*) FROM requests;  -- returns 10
```

### Issue: `reviewers` table missing `utc_id` column
The dump was created before PR #18 was merged, which added the `utc_id` column to the `reviewers` table. The current `main.py` references `r.utc_id` in `GET /api/reviewers`, so the endpoint would crash without this column.
**Fix applied locally:**
```sql
ALTER TABLE reviewers ADD COLUMN utc_id TEXT;
INSERT INTO reviewers (reviewer_name, utc_id) VALUES ('Test Reviewer', 'rev001');
```
**This only affects your local database — no repo files were changed.**
**Action needed:** Melissa should either update the dump to include this column, or the team should agree on a standard setup SQL to run after restore.

---

## 5. Starting the Backend

```bash
dotenv run -- uvicorn app.main:app --port 8001 --reload
```

Must use `dotenv run --` so the `.env` file is loaded before Python reads `os.environ["DATABASE_URL"]`.

---

## 6. Current State After Setup

| Area | Status |
|---|---|
| Frontend running | ✅ `npm run dev` on port 5173 |
| Backend running | ✅ uvicorn on port 8001 |
| Database connected | ✅ ai_db_demo with 10 cases |
| Student login (`CASE01`–`CASE10`) | ✅ Works |
| Reviewer login (`rev001`) | ✅ Works |
| Cases list on dashboards | ✅ Works |
| Student case view | ✅ Works |
| AI Recommendation section on reviewer page | ❌ Empty — see below |

---

## 7. Outstanding Issue — AI Recommendation Section Missing

**What you see:** The reviewer opens a case and the "AI Recommendation" section is not shown.

**Root cause:** All 9 active cases in the database are in `ready_for_decision` status. This means:
- Documents were uploaded ✅
- Extraction ran and produced grounded evidence (84 rows in DB) ✅
- **Decision engine was never triggered on these specific records** ❌

The prepopulated dump was created before the decision engine was connected to the extraction pipeline (which happened in PR #16). Melissa's `demo_results.csv` shows 11 cases with decisions, but those results were from a separate test run with different case UUIDs — they are not in the dump.

**Proof:**
```sql
SELECT status, COUNT(*) FROM requests GROUP BY status;
--  ready_for_decision | 9
--  needs_info         | 1

SELECT COUNT(*) FROM decision_results;
-- 0
```

**The fix:** A script `trigger_decisions.py` has been written and is ready to run. It loops over all `ready_for_decision` cases, finds their completed extraction run, runs `decide(packet)` using the existing grounded evidence, and stores the result — without re-processing any PDFs.

**Do NOT run this yet** — confirm with teammates first that:
1. Everyone has restored the prepopulated DB
2. It's okay to trigger decisions on the demo cases
3. Melissa doesn't want to include pre-run decisions in an updated dump instead

---

## 8. Items Still Needed

| Item | Owner | Notes |
|---|---|---|
| `uploads_demo.zip` | Melissa | Required for uploading new documents. Download from shared drive and extract to `Data/Uploads/`. |
| Updated dump with `utc_id` column | Melissa | Current dump is missing this column from PR #18. |
| Decision results in dump | Team decision | Either run `trigger_decisions.py` locally or Melissa updates the dump. |
| Reviewer records with `utcId` | Melissa | The dump has no reviewer rows. Each teammate must manually insert one for now. |

---

## 9. Login Credentials (Local Testing)

**Students:**
| UTC ID | Name | Case Type |
|---|---|---|
| CASE01 | Alice Johnson | Approve |
| CASE02 | Brian Lee | Needs Info |
| CASE03 | Carla Gomez | Needs Info |
| CASE04 | Daniel Kim | Deny |
| CASE09 | Ivan Novak | Needs Info |

**Reviewer:**
| UTC ID | Note |
|---|---|
| `rev001` | Manually inserted — assigned to all cases |
