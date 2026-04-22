DROP DATABASE IF EXISTS ai_db_demo;
CREATE DATABASE ai_db_demo;

\connect ai_db_demo
\i db_schema.sql
INSERT INTO reviewers (reviewer_name, utc_id, created_at)
VALUES
  ('Avery Chen',   'rev001', now()),
  ('Maya Patel',   'rev002', now()),
  ('Noah Johnson', 'rev003', now()),
  ('Liam Torres',  'rev004', now()),
  ('Sara Kim',     'rev005', now()),
  ('David Wright', 'rev006', now())
ON CONFLICT (utc_id) DO NOTHING;