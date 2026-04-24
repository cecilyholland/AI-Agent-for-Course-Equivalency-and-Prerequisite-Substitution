-- Seed reviewers with plain-text passwords.
-- The backend's seed_database.py hashes these on startup.
INSERT INTO reviewers (reviewer_name, utc_id, password_hash, role, created_at)
VALUES
  ('Avery Chen',   'rev001', 'password123', 'admin',    now()),
  ('Maya Patel',   'rev002', 'password123', 'reviewer', now()),
  ('Noah Johnson', 'rev003', 'password123', 'reviewer', now()),
  ('Liam Torres',  'rev004', 'password123', 'reviewer', now()),
  ('Sara Kim',     'rev005', 'password123', 'reviewer', now()),
  ('David Wright', 'rev006', 'password123', 'reviewer', now())
ON CONFLICT (utc_id) DO NOTHING;
