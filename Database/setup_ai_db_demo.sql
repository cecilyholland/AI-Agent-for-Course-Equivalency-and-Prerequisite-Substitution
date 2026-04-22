DROP DATABASE IF EXISTS ai_db_demo;
CREATE DATABASE ai_db_demo;

\connect ai_db_demo
\i db_schema.sql
INSERT INTO reviewers (reviewer_name, utc_id, password_hash, role, created_at)
VALUES
  ('Avery Chen',   'rev001', 'password123', 'admin',    now()),
  ('Maya Patel',   'rev002', 'password123', 'reviewer', now()),
  ('Noah Johnson', 'rev003', 'password123', 'reviewer', now()),
  ('Liam Torres',  'rev004', 'password123', 'reviewer', now()),
  ('Sara Kim',     'rev005', 'password123', 'reviewer', now()),
  ('David Wright', 'rev006', 'password123', 'reviewer', now())
ON CONFLICT (utc_id) DO NOTHING;

-- Courses are seeded from Data/Processed/ParsedData.csv via POST /api/courses/seed-from-csv