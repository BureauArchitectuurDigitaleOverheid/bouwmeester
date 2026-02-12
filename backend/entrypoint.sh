#!/bin/sh
set -e

# Activate the venv directly — avoids uv run which tries to
# re-install the project and fails on read-only .pth files.
export PATH="/app/.venv/bin:$PATH"

echo "Running database migrations..."
alembic upgrade head

echo "Starting uvicorn..."
exec uvicorn bouwmeester.core.app:create_app --factory --host 0.0.0.0 --port 8080
