-- =============================================
-- CLEAN DEMO DATABASE SETUP
-- Drops and recreates ai_db_demo
-- =============================================

-- Run from postgres DB:
-- psql -U melissastan -d postgres -f setup_ai_db_demo.sql

DROP DATABASE IF EXISTS ai_db_demo;
CREATE DATABASE ai_db_demo;

\connect ai_db_demo

-- =============================================
-- Load schema
-- =============================================
\i db_schema.sql

-- =============================================
-- Insert Reviewers (with required utc_id)
-- =============================================

INSERT INTO reviewers (reviewer_name, utc_id, created_at)
VALUES
  ('Alice Reviewer',  'rev001', now()),
  ('Brian Reviewer',  'rev002', now()),
  ('Carla Reviewer',  'rev003', now()),
  ('Daniel Reviewer', 'rev004', now()),
  ('Elena Reviewer',  'rev005', now())
ON CONFLICT (utc_id) DO NOTHING;

-- =============================================
-- Insert Demo Cases (CASE01–CASE10)
-- =============================================

INSERT INTO requests (
  student_id,
  student_name,
  course_requested,
  status,
  created_at,
  updated_at
)
VALUES
  ('CASE01','Alice Johnson','CPSC 5450 - Machine Learning','uploaded',now(),now()),
  ('CASE02','Brian Lee','CPSC 5530 - Data Visualization','uploaded',now(),now()),
  ('CASE03','Carla Gomez','CPSC 5520 - Database Systems','uploaded',now(),now()),
  ('CASE04','Daniel Kim','CPSC 5600 - Distributed Systems','uploaded',now(),now()),
  ('CASE05','Elena Martinez','CPSC 5710 - Computer Networks','uploaded',now(),now()),
  ('CASE06','Farah Ahmed','CPSC 5800 - Artificial Intelligence','uploaded',now(),now()),
  ('CASE07','George Patel','CPSC 5310 - Software Engineering','uploaded',now(),now()),
  ('CASE08','Hannah Wright','CPSC 5400 - Operating Systems','uploaded',now(),now()),
  ('CASE09','Ivan Novak','CPSC 5470 - Natural Language Processing','uploaded',now(),now()),
  ('CASE10','Julia Chen','CPSC 5890 - Advanced Topics in AI','uploaded',now(),now());

-- =============================================
-- Assign Each Case to a Reviewer (Round Robin)
-- =============================================

WITH ordered_cases AS (
  SELECT request_id,
         ROW_NUMBER() OVER (ORDER BY student_id) AS rn
  FROM requests
  WHERE student_id LIKE 'CASE%'
),
ordered_reviewers AS (
  SELECT reviewer_id,
         ROW_NUMBER() OVER (ORDER BY utc_id) AS rn
  FROM reviewers
),
reviewer_count AS (
  SELECT COUNT(*) AS total FROM ordered_reviewers
)
UPDATE requests r
SET assigned_reviewer_id = orv.reviewer_id,
    updated_at = now()
FROM ordered_cases oc
JOIN reviewer_count rc ON true
JOIN ordered_reviewers orv
  ON orv.rn = ((oc.rn - 1) % rc.total) + 1
WHERE r.request_id = oc.request_id;

-- =============================================
-- Done
-- =============================================