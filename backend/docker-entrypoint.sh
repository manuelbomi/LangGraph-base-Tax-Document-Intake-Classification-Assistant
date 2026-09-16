#!/usr/bin/env sh
set -e

echo "[entrypoint] running Alembic migrations..."
alembic upgrade head

echo "[entrypoint] seeding prompt registry (v1 prompts, no-op if already active)..."
python -m app.prompts.seed_prompts

echo "[entrypoint] loading fictitious clients + expected-documents checklists..."
python -m scripts.seed_clients

echo "[entrypoint] seeding example documents (no-op if already present)..."
python -m scripts.seed_examples

echo "[entrypoint] starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
