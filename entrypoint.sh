#!/bin/sh
set -e

echo "Running full database seed (passwords, courses, cases 1-10)..."
python Database/seed_database.py

echo "Starting backend server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
