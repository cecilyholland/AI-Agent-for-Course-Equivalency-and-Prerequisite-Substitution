-- =============================================
-- CLEAN DEMO DATABASE SETUP
-- Drops and recreates ai_db_demo
-- =============================================

-- Must be connected to postgres DB, not ai_db_demo
-- Example:
-- psql -U melissastan -d postgres -f setup_ai_db_demo.sql

-- 1) Drop database if exists
DROP DATABASE IF EXISTS ai_db_demo;

-- 2) Create fresh database
CREATE DATABASE ai_db_demo;

-- =============================================
-- Switch connection to new DB
-- =============================================
\connect ai_db_demo

-- 3) Load schema
\i db_schema.sql

-- =============================================
-- OPTIONAL: Insert Student Names for Demo
-- (Only if CASE01–CASE10 already exist in this DB)
-- =============================================

UPDATE requests SET student_name = 'Alice Johnson'  WHERE student_id = 'CASE01';
UPDATE requests SET student_name = 'Brian Lee'      WHERE student_id = 'CASE02';
UPDATE requests SET student_name = 'Carla Gomez'    WHERE student_id = 'CASE03';
UPDATE requests SET student_name = 'Daniel Kim'     WHERE student_id = 'CASE04';
UPDATE requests SET student_name = 'Elena Martinez' WHERE student_id = 'CASE05';
UPDATE requests SET student_name = 'Farah Ahmed'    WHERE student_id = 'CASE06';
UPDATE requests SET student_name = 'George Patel'   WHERE student_id = 'CASE07';
UPDATE requests SET student_name = 'Hannah Wright'  WHERE student_id = 'CASE08';
UPDATE requests SET student_name = 'Ivan Novak'     WHERE student_id = 'CASE09';
UPDATE requests SET student_name = 'Julia Chen'     WHERE student_id = 'CASE10';

-- =============================================
-- Done
-- =============================================