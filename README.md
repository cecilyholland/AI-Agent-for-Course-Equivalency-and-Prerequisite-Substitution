# AI Agent for Course Equivalency and Prerequisite Substitution

Universities face slow, error-prone course equivalency reviews due to fragmented evidence and nuanced criteria. This project builds a secure AI agent that turns messy documents into cited decision packets with clear reasoning, privacy safeguards, and an auditable, human-reviewed workflow.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Quick Start](#quick-start)
- [Backend (FastAPI)](#backend-fastapi)
- [Frontend (React/Vite)](#frontend-reactvite)
- [Database (PostgreSQL)](#database-postgresql)
- [Extraction Pipeline](#extraction-pipeline)
- [Decision Engine](#decision-engine)
- [Security](#security)
- [Case Workflow](#case-workflow)
- [Project Structure](#project-structure)
- [Environment Variables](#environment-variables)
- [Testing](#testing)

---

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Frontend     │────▶│  FastAPI Backend │────▶│   PostgreSQL    │
│  (React/Vite)   │     │    (app/)        │     │   (ai_db)       │
└─────────────────┘     └────────┬─────────┘     └─────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
            ┌───────────┐ ┌───────────┐ ┌───────────┐
            │ Extraction│ │  Decision │ │  Security │
            │  Pipeline │ │   Engine  │ │   Filter  │
            └───────────┘ └───────────┘ └───────────┘
```

**Data Flow:**
1. Student uploads PDF(s) → `POST /api/cases` → creates Request + Document rows
2. Extraction pipeline parses PDFs → stores citation chunks + grounded evidence
3. Decision engine evaluates evidence → produces scored recommendation
4. Reviewer reviews AI decision → approves, denies, or requests more info
5. Committee votes (if escalated) → final decision

---

## Quick Start

### Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.10+ |
| Node.js | 18+ |
| PostgreSQL | 14+ |
| Tesseract OCR | Latest (for scanned PDFs) |
| Poppler | Latest (for PDF to image) |

### 1. Database Setup

```bash
# Create database
createdb ai_db

# Load schema
psql -U <username> -d ai_db -f Database/db_schema.sql
```

### 2. Backend Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install fastapi uvicorn sqlalchemy psycopg2-binary python-multipart python-dotenv pdfplumber pytesseract pdf2image

# Set environment variable
export DATABASE_URL="postgresql+psycopg2://<username>@localhost:5432/ai_db"

# Run server
cd app && uvicorn main:app --reload
```

API docs: http://127.0.0.1:8000/docs

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:5173

---

## Backend (FastAPI)

The backend (`app/`) provides REST APIs for case management, document upload, extraction, and review workflows.

### Key Files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI routes and workflow orchestration |
| `models.py` | SQLAlchemy ORM models |
| `schemas.py` | Pydantic request/response schemas |

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/cases` | Create new case with document upload |
| `GET` | `/api/cases` | List cases (filtered by role/student) |
| `GET` | `/api/cases/{id}` | Get case details |
| `POST` | `/api/cases/{id}/documents` | Upload additional documents |
| `POST` | `/api/cases/{id}/extraction/start` | Trigger extraction pipeline |
| `POST` | `/api/cases/{id}/extraction/complete` | Complete extraction with facts |
| `GET` | `/api/cases/{id}/decision/result/latest` | Get latest AI recommendation |
| `POST` | `/api/cases/{id}/review` | Submit reviewer action |

---

## Frontend (React/Vite)

React 18 single-page application for students and reviewers.

### Pages

| Page | Role | Purpose |
|------|------|---------|
| `LoginPage` | All | UTC ID + role selection |
| `StudentDashboard` | Student | List of student's cases |
| `StudentCaseView` | Student | Case detail + upload for NEEDS_INFO |
| `StudentNewCase` | Student | Submit new equivalency request |
| `ReviewerDashboard` | Reviewer | All cases table |
| `ReviewerCaseReview` | Reviewer | Case detail + action panel + audit log |

### Components

| Component | Purpose |
|-----------|---------|
| `DecisionExplanation` | Shows AI reasoning with citations |
| `DecisionSummaryCard` | Score and decision overview |
| `ReviewerActionPanel` | Approve/Deny/Needs More Info buttons |
| `CitationBlock` | Displays source text excerpts |
| `GapList` | Shows identified gaps in evidence |
| `AuditLogTimeline` | Timestamped activity log |
| `StatusBadge` | Colored badge for case status |

### Running

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api/*` requests to the backend automatically.

---

## Database (PostgreSQL)

### Core Tables

| Table | Purpose |
|-------|---------|
| `requests` | Case/request records with status tracking |
| `documents` | Uploaded PDF metadata (filename, hash, path) |
| `transcripts` | Student transcript data (grade, term) |
| `extraction_runs` | Tracks extraction pipeline executions |
| `citation_chunks` | Text excerpts from source documents |
| `grounded_evidence` | Extracted facts with unknown flag |
| `evidence_citations` | Links facts to supporting chunks (M:N) |
| `decision_runs` | Decision engine executions |
| `decision_results` | AI recommendations (JSON) |
| `review_actions` | Human reviewer decisions |
| `reviewers` | Reviewer accounts |
| `case_committee` | Committee member assignments |
| `committee_votes` | Committee voting records |

### Entity Relationships

```
requests
  ├── documents (1:N)
  ├── transcripts (1:N)
  ├── extraction_runs (1:N)
  │     ├── citation_chunks (1:N)
  │     └── grounded_evidence (1:N)
  │           └── evidence_citations (M:N) ──▶ citation_chunks
  ├── decision_runs (1:N)
  │     └── decision_results (1:1)
  ├── review_actions (1:N)
  └── case_committee (1:N) ──▶ reviewers
        └── committee_votes (1:N)
```

### Setup Commands

```bash
# Create database
createdb ai_db

# Load schema
psql -U <username> -d ai_db -f Database/db_schema.sql

# Reset database
dropdb ai_db && createdb ai_db && psql -U <username> -d ai_db -f Database/db_schema.sql
```

---

## Extraction Pipeline

The extraction module (`app/extraction/`) parses PDFs and extracts structured facts with citations.

### Module Structure

| File | Purpose |
|------|---------|
| `pipeline.py` | Orchestrates extraction, writes to DB |
| `pdf_text.py` | PDF text extraction + OCR fallback |
| `chunking.py` | Text chunking for citations |
| `syllabus_parser.py` | Extract facts from syllabi |
| `catalog_parser.py` | Extract course candidates from catalogs |
| `transcript_parser.py` | Extract grades and terms from transcripts |

### Extracted Facts

| Fact Type | Source | Fields |
|-----------|--------|--------|
| Course info | Syllabus | code, title, credits, description, prerequisites, learning_outcomes |
| Topics | Syllabus/Catalog | topic list |
| Outcomes | Syllabus | learning outcome list |
| Grade | Transcript | letter grade (A, B+, etc.) |
| Term | Transcript | term taken (Fall 2022, etc.) |

### OCR Fallback Chain

1. **pdfplumber** - Extracts embedded text (fast)
2. **ocrmypdf** - Creates searchable PDF via Tesseract
3. **pytesseract + pdf2image** - Direct OCR to text

### Usage

```bash
# Run extraction for a request
python -m app.extraction run <request_id>

# Validate extraction outputs
python -m app.extraction validate <request_id>
```

### Dependencies

**Python packages:**
```bash
pip install pdfplumber pytesseract pdf2image python-dotenv sqlalchemy
```

**System dependencies:**
- Tesseract OCR: `brew install tesseract` / `choco install tesseract`
- Poppler: `brew install poppler` / `choco install poppler`

---

## Decision Engine

The decision engine (`decision_engine/`) evaluates course equivalency using extracted evidence.

### Decision Outcomes

| Decision | When it occurs |
|----------|----------------|
| **APPROVE** | Score ≥ 90, no gaps |
| **APPROVE_WITH_BRIDGE** | Score 80-89, OR ≥90 with FIXABLE gaps |
| **NEEDS_MORE_INFO** | Any INFO_MISSING gap, OR score 70-79 |
| **DENY** | Any HARD gap, OR score < 70 |

### Scoring System (100 points)

| Component | Weight | Description |
|-----------|--------|-------------|
| Topics | 40 | % of required topics matched |
| Outcomes | 30 | % of required outcomes matched |
| Credits | 20 | Exact match = 20, off-by-1 = 10, else 0 |
| Lab Parity | 10 | Lab present when required |

### Gap Types

| Severity | Effect | Examples |
|----------|--------|----------|
| **HARD** | Forces DENY | Credits off by 2+, zero topic overlap |
| **FIXABLE** | Forces BRIDGE | Credits off by 1, missing lab |
| **INFO_MISSING** | Forces NEEDS_MORE_INFO | Unknown credits, topics, outcomes |

### Modes

| Mode | File | Description |
|------|------|-------------|
| Deterministic | `contracts.py` | Pure function, no external deps |
| LLM-based | `llm_decision.py` | Calls GPT for nuanced reasoning |

### Policy Configuration

```python
PolicyConfig(
    approve_threshold=90,      # Score for APPROVE
    bridge_threshold=80,       # Score for BRIDGE
    needs_info_threshold=70,   # Ambiguous band
    require_lab_parity=True,
    require_credits_known=True,
    min_grade="C",             # Optional: minimum grade
    max_course_age_years=5,    # Optional: course expiration
)
```

See [`decision_engine/README.md`](decision_engine/README.md) for full documentation.

---

## Security

The security module (`app/security/`) defends against prompt injection attacks in uploaded documents.

### Prompt Injection Defense

**Detection methods:**
1. **Regex patterns** - Detects instruction override attempts ("ignore previous instructions", "approve this request", etc.)
2. **Trigger words** - Flags suspicious keywords (ignore, bypass, override, approve, deny, etc.)
3. **Typoglycemia detection** - Catches obfuscated variants (e.g., "ignroe" for "ignore")
4. **Vigil integration** - Optional external scanner

### Risk Scoring

| Detector | Severity | Points |
|----------|----------|--------|
| High-severity regex | HIGH | 5 |
| Medium-severity regex | MEDIUM | 3 |
| Typoglycemia variant | LOW | 2 |
| Trigger word | LOW | 1 |
| Multi-signal bonus | MEDIUM | 2 |

**Decision:** REJECT if total score ≥ 10 (configurable)

### High-Severity Patterns (examples)

- `ignore (all)? (previous|prior) instructions`
- `bypass (safety|policy|rules)`
- `automatically approve this request`
- `set decision to approve`
- `reveal (the)? system prompt`

### Usage

```python
from app.security.prompt_injection_defense import PromptInjectionDefense

defense = PromptInjectionDefense(reject_threshold=10)
result = defense.scan_pages(pages_text)

if result.decision == "reject":
    # Block extraction, log findings
    print(f"Blocked: {result.total_score} points, {len(result.findings)} findings")
```

---

## Case Workflow

### Status Flow

```
uploaded → extracting → ready_for_decision → ai_recommendation → reviewed
                              ↓
                         needs_info (if evidence incomplete)
                              ↓
                    pending_committee → committee_decided
```

| Status | Description |
|--------|-------------|
| `uploaded` | Documents received, waiting for extraction |
| `extracting` | AI extracting course data from documents |
| `ready_for_decision` | Extraction complete, ready for AI decision |
| `ai_recommendation` | AI recommendation ready for reviewer |
| `needs_info` | Reviewer requested additional documents |
| `reviewed` | Reviewer made final decision |
| `pending_committee` | Escalated to committee review |
| `committee_decided` | Committee reached final decision |

### Committee Voting

When a case is escalated:
1. 3 committee members assigned (excluding case reviewer)
2. Members vote independently (blind voting)
3. Majority rule with conservative tiebreaking: DENY > NEEDS_MORE_INFO > BRIDGE > APPROVE

---

## Project Structure

```
├── app/
│   ├── main.py                 # FastAPI routes
│   ├── models.py               # SQLAlchemy models
│   ├── schemas.py              # Pydantic schemas
│   ├── extraction/             # PDF parsing pipeline
│   │   ├── pipeline.py
│   │   ├── pdf_text.py
│   │   ├── chunking.py
│   │   ├── syllabus_parser.py
│   │   ├── catalog_parser.py
│   │   └── transcript_parser.py
│   └── security/               # Prompt injection defense
│       └── prompt_injection_defense.py
├── decision_engine/
│   ├── contracts.py            # Deterministic decision logic
│   └── llm_decision.py         # LLM-based decisions
├── frontend/
│   ├── src/
│   │   ├── components/         # React components
│   │   ├── pages/              # Page components
│   │   └── services/           # API client
│   └── vite.config.js
├── Database/
│   ├── db_schema.sql           # PostgreSQL schema
│   └── DatabaseREADME.md
├── Data/
│   ├── Raw/                    # Source documents (immutable)
│   └── Processed/              # Extraction outputs
└── demo_cases/                 # Test payloads
```

---

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `UPLOAD_DIR` | Directory for uploaded files | No (default: `./uploads`) |
| `POPPLER_PATH` | Path to Poppler bin directory | Windows only |
| `OPENAI_API_KEY` | For LLM decision mode | If using LLM |

**Example:**
```bash
export DATABASE_URL="postgresql+psycopg2://postgres@localhost:5432/ai_db"
export UPLOAD_DIR="./uploads"
```

---

## Testing

### Demo Test Cases

Test payloads in `demo_cases/*.json` cover various scenarios:

| File | Scenario |
|------|----------|
| `case01_approve_full.json` | Full evidence, should approve |
| `case02_needs_info_missing_credits.json` | Missing credits |
| `case07_prompt_injection_example.json` | Security edge case |
| `case10_bridge_candidate.json` | Bridge scenario |

### Run Demo Tests

```bash
# Start backend first
cd app && uvicorn main:app --reload

# Run all demo cases
python run_demo_cases.py --base-url http://127.0.0.1:8000
```

Results output to `demo_results/`.

---

## Citation/Grounding Policy

All AI decisions must be traceable to source documents:

- Evidence stored in `grounded_evidence` with `unknown=true/false` flag
- Citations link evidence to `citation_chunks` (page number, text spans)
- Files in `Data/Raw/` are immutable source documents
- Processed artifacts go in `Data/Processed/`

This ensures every recommendation can be audited back to specific text in uploaded documents.
