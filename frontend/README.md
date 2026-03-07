# Frontend — Course Equivalency & Prerequisite Substitution

React 18 + Vite single-page application for the UTC Course Equivalency system.
Students submit course-equivalency requests and track their status. Reviewers review AI-recommended decisions and approve, deny, or request more information.

---

## Prerequisites

| Tool | Version |
|------|---------|
| Node.js | 18+ |
| npm | 9+ |
| Python | 3.11+ |
| PostgreSQL | 14+ (or SQLite for local dev) |

---

## Project Structure

```
frontend/
├── public/
├── src/
│   ├── components/
│   │   ├── AuditLogTimeline.jsx   # Timestamped activity log shown to reviewers
│   │   ├── DecisionExplanation.jsx
│   │   ├── DecisionSummaryCard.jsx
│   │   ├── ReviewerActionPanel.jsx # Approve / Deny / Needs More Info panel
│   │   ├── StatusBadge.jsx        # Colored badge for case status
│   │   ├── CitationBlock.jsx
│   │   └── GapList.jsx
│   ├── pages/
│   │   ├── LoginPage.jsx          # UTC ID + role login
│   │   ├── StudentDashboard.jsx   # Student: list of their cases
│   │   ├── StudentCaseView.jsx    # Student: case detail + upload for NEEDS_INFO
│   │   ├── StudentNewCase.jsx     # Student: submit a new request (PDF upload)
│   │   ├── ReviewerDashboard.jsx  # Reviewer: all cases table
│   │   └── ReviewerCaseReview.jsx # Reviewer: case detail + action panel + audit log
│   ├── services/
│   │   ├── api.js                 # All fetch() calls to the FastAPI backend
│   │   └── auth.jsx               # AuthContext (login / logout / session)
│   ├── App.jsx                    # Router + NavBar + protected routes
│   └── main.jsx
├── vite.config.js                 # Dev server + API proxy config
└── package.json
```

---

## Running the Full Stack

The frontend communicates with the FastAPI backend via a **Vite dev-server proxy** — all `/api/*` requests are forwarded automatically. You need the backend running before the frontend will work.

### Step 1 — Start PostgreSQL

Make sure PostgreSQL is running on your machine. The default setup uses a database named `ai_db`.

If you need to create it:

```bash
psql -U postgres -c "CREATE DATABASE ai_db;"
```

Run the schema (only needed once):

```bash
psql -U postgres -d ai_db -f Database/db_schema.sql
```

> **Note:** If your PostgreSQL password contains special characters (e.g. `@`), URL-encode them in `DATABASE_URL`.
> Example: `password123@abc` → `password123%40abc`

---

### Step 2 — Start the Backend

```bash
cd app
pip install fastapi sqlalchemy uvicorn python-multipart psycopg2-binary
```

Set the database URL and start the server:

```bash
# PostgreSQL
DATABASE_URL="postgresql://postgres:<password>@localhost:5432/ai_db" uvicorn main:app --reload --port 8001

# SQLite (local dev, no PostgreSQL needed)
uvicorn main:app --reload --port 8001
```

> The backend defaults to SQLite (`app.db`) if `DATABASE_URL` is not set.

Verify it is running: [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs)

---

### Step 3 — Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

The app will be available at [http://localhost:5173](http://localhost:5173).

The Vite dev server proxies all `/api` calls to `http://127.0.0.1:8001`, so no CORS configuration is needed.

---

## API Proxy

Configured in `vite.config.js`:

```js
server: {
  proxy: {
    '/api': {
      target: 'http://127.0.0.1:8001',
      changeOrigin: true,
    },
  },
}
```

| Frontend call | Forwarded to |
|---------------|-------------|
| `GET /api/cases` | `http://127.0.0.1:8001/api/cases` |
| `GET /api/cases/:id` | `http://127.0.0.1:8001/api/cases/:id` |
| `POST /api/cases` | `http://127.0.0.1:8001/api/cases` |
| `POST /api/cases/:id/documents` | `http://127.0.0.1:8001/api/cases/:id/documents` |
| `POST /api/cases/:id/review` | `http://127.0.0.1:8001/api/cases/:id/review` |

---

## Login

On the login page, enter any non-empty UTC ID and select a role:

- **Student** — accesses their own cases using the UTC ID as `studentId`
- **Reviewer** — accesses all cases and can take actions

No password is required. Student accounts are validated against the database when cases are fetched.

---

## Case Status Flow

| Status | Meaning |
|--------|---------|
| `UPLOADED` | Documents received, waiting for extraction |
| `EXTRACTING` | AI agent is extracting course data from documents |
| `READY_FOR_DECISION` | Extraction complete, AI is generating recommendation |
| `AI_RECOMMENDATION` | AI recommendation is ready for reviewer |
| `REVIEW_PENDING` | Reviewer has been assigned, awaiting action |
| `NEEDS_INFO` | Reviewer requested additional documents from student |
| `REVIEWED` | Reviewer made a final decision (approve or deny) |

On the student's case view, `REVIEWED` is shown as **Approved** or **Denied** based on the reviewer's last action.

---

## File Upload Requirements

All document uploads (new case and additional info) accept **PDF files only**. Non-PDF files are rejected with an error message before submission.

---

## Build for Production

```bash
cd frontend
npm run build
```

Output is in `frontend/dist/`. Serve it with any static file server or configure FastAPI to serve it directly.
