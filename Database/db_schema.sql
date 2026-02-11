-- allows postgres to generate UUID
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- use this when student makes a request to upload their documents
CREATE TABLE requests (
  request_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id      TEXT NOT NULL,
  student_name    TEXT,
  course_requested TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- this status tells us what part the system is at
  status          TEXT NOT NULL CHECK (status IN (
                    'uploaded',
                    'extracting',
                    'ready_for_decision',
                    'needs_info',
                    'ai_recommendation',
                    'review_pending',
                    'reviewed'
                  ))
);

-- help filter the request based on status
CREATE INDEX idx_requests_status ON requests(status);


-- this table stores information about each uploaded PDF. The PDF does not get stored here, only metadata
-- know which request the file belongs to, know where the file is stored, verify integrity, and support multiple uploads per request
CREATE TABLE documents (
-- every PDF upload gets its own doc_id
  doc_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
--   links this document to a request (this cannot be null)
  request_id      UUID NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  filename        TEXT NOT NULL,
  content_type    TEXT NOT NULL DEFAULT 'application/pdf',
  sha256          TEXT NOT NULL,   -- store hex string
  storage_uri     TEXT NOT NULL,   -- where the actual file lives (put local path)
  size_bytes      BIGINT,

  -- helpful in multi-upload cycles. If the user uploads a new PDF, old one stays in DB but is marked inactive
  is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

-- lets the database quickly find all documents that belong to a given request
CREATE INDEX idx_documents_request_id ON documents(request_id);
-- lets the database quickly find documents by their file hash. Helps with duplicate uploads
CREATE INDEX idx_documents_sha256 ON documents(sha256);


-- tracks each attempt to run Cecily’s extraction pipeline
-- records each extraction attempt so we know what ran, what failed, and where the evidence came from
CREATE TABLE extraction_runs (
  extraction_run_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id         UUID NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  started_at         TIMESTAMPTZ,
  finished_at        TIMESTAMPTZ,
  status             TEXT NOT NULL CHECK (status IN (
                      'queued', 'running', 'completed', 'failed'
                    )),
  error_message      TEXT,

  -- where the extraction manifest file is stored
  manifest_uri       TEXT,
  manifest_sha256    TEXT
);
-- find all extraction runs for a given request
CREATE INDEX idx_extraction_runs_request_id ON extraction_runs(request_id);
-- find extraction runs by their current state
CREATE INDEX idx_extraction_runs_status ON extraction_runs(status);


-- citation_chunks stores the exact pieces of text that support extracted facts
CREATE TABLE citation_chunks (
  -- Surrogate primary key (DB identity)
  chunk_uuid         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  -- Deterministic content-based ID (SHA of doc_id + run_id + span + text)
  chunk_sha_id       TEXT NOT NULL UNIQUE,
  doc_id             UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
--   every chunk must belong to one specific extraction run
-- REFERENCES extraction_runs(extraction_run_id): this creates a link to the extraction_runs table. the extraction must exist in order for a chunk to be created. If an extraction run is deleted, all chunks created by that run are automatically deleted too.
  extraction_run_id  UUID NOT NULL REFERENCES extraction_runs(extraction_run_id) ON DELETE CASCADE,
  page_num           INT, -- the page number in the PDF where this chunk appears
--   tells us where the chunk starts and ends
  span_start         INT,
  span_end           INT,
-- a short excerpt of the chunk in case the reviewer wants to see it
  snippet_text       TEXT,             -- short excerpt for UI
  full_text          TEXT,             -- optional (can omit if too large)
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- this index lets the database quickly find all chunks that came from a specific document
CREATE INDEX idx_chunks_doc_id ON citation_chunks(doc_id);
-- this index lets the database quickly find all chunks created by a specific extraction run
CREATE INDEX idx_chunks_run_id ON citation_chunks(extraction_run_id);


-- grounded_evidence table stores structured facts extracted from documents, links them to their extraction run and request, and explicitly records whether each fact is known or unknown.
-- meaning stores the extracted facts that the decision engine reasons over
CREATE TABLE grounded_evidence (
  evidence_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- Unique ID for a single evidence item (fact)
  request_id         UUID NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,
  -- tells us which run produced this fact
  extraction_run_id  UUID NOT NULL REFERENCES extraction_runs(extraction_run_id) ON DELETE CASCADE,

  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- what is the fact about?
  -- describes what kind of fact this is
  fact_type          TEXT NOT NULL,   -- ex: 'credits', 'outcome', 'topic', 'assessment'
  fact_key           TEXT,            -- optional stable key (e.g., "credits_total", "required_prerequisites")
  fact_value         TEXT,            -- normalized value if simple
  fact_json          JSONB,           -- helps formating the fact into a json format
-- “Evidence valid?” gate. Indicates whether the value could not be determined from the documents
    -- FALSE: fact is known and supported
    -- TRUE: fact is missing or unclear
  unknown            BOOLEAN NOT NULL DEFAULT FALSE,
  -- optional and not required
  notes              TEXT
);

-- lets the database quickly find all evidence for one request
CREATE INDEX idx_evidence_request_id ON grounded_evidence(request_id);
-- lets the database quickly find evidence produced by a specific extraction run
CREATE INDEX idx_evidence_run_id ON grounded_evidence(extraction_run_id);
-- lets the database quickly filter evidence by type
CREATE INDEX idx_evidence_fact_type ON grounded_evidence(fact_type);


-- evidence_citations connects extracted facts to the exact text that supports them.
    --One fact can be supported by multiple chunks
    --One chunk can support multiple facts
-- fact and chunk many-to-many relationship
CREATE TABLE evidence_citations (
  -- Each row points to one extracted fact, where that fact must exist in grounded_evidence
  evidence_id   UUID NOT NULL REFERENCES grounded_evidence(evidence_id) ON DELETE CASCADE,
  -- Each row points to one citation chunk, where that chunk must exist
  chunk_uuid      UUID NOT NULL REFERENCES citation_chunks(chunk_uuid) ON DELETE CASCADE,
-- this is primary key. You cannot link the same fact to the same chunk twice. Each (evidence_id, chunk_uuid) pair is unique
  PRIMARY KEY (evidence_id, chunk_uuid)
);

-- Index for reverse lookups
CREATE INDEX idx_evidence_citations_chunk_uuid ON evidence_citations(chunk_uuid);


-- decision_runs tracks each time the decision engine is run for a request. it helps to re-run
CREATE TABLE decision_runs (
  decision_run_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
--   links this decision run to a request
  request_id         UUID NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,

  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  started_at         TIMESTAMPTZ,
  finished_at        TIMESTAMPTZ,
-- current state of the decision run
  status             TEXT NOT NULL CHECK (status IN (
                      'queued', 'running', 'completed', 'failed'
                    )),
-- optional
  error_message      TEXT,

  -- store the input packet used (optional)
  decision_inputs    JSONB
);

-- allows the database to quickly find all decision runs for a given request
CREATE INDEX idx_decision_runs_request_id ON decision_runs(request_id);
-- allows the database to quickly find decision runs by their current state
CREATE INDEX idx_decision_runs_status ON decision_runs(status);


-- storing the decision engine's output
CREATE TABLE decision_results (
  -- each decision run has one one decision result
  decision_run_id     UUID PRIMARY KEY REFERENCES decision_runs(decision_run_id) ON DELETE CASCADE,

  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- storing it in json
  result_json         JSONB NOT NULL,

  -- workflow signal from engine
  needs_more_info     BOOLEAN NOT NULL DEFAULT FALSE,
  -- optional but col ddbe useful to have like "credit_hours"
  missing_fields      JSONB                -- list of fields needed, if any
);


-- review_actions records what a human reviewer did
CREATE TABLE review_actions (
  review_action_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id          UUID NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,

  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  reviewer_id         TEXT,
  action             TEXT NOT NULL CHECK (action IN ('approve', 'deny', 'request_info', 'override')),
  comment            TEXT NOT NULL,

  -- optional: what decision_run/result this action relates to
  -- if the decision run is deleted, the review action stays, but its link to that run is cleared
  decision_run_id     UUID REFERENCES decision_runs(decision_run_id) ON DELETE SET NULL
);

-- find all reviewer actions for a specific request
CREATE INDEX idx_review_actions_request_id ON review_actions(request_id);
-- find review actions by type
CREATE INDEX idx_review_actions_action ON review_actions(action);
