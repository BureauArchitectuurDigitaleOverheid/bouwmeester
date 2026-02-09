#!/bin/sh
set -e

echo "Running database migrations..."
uv run alembic upgrade head

if [ "${SEED_ON_STARTUP:-false}" = "true" ]; then
    echo "Seeding database..."
    uv run python scripts/seed.py
fi

echo "Starting uvicorn..."
exec uv run uvicorn bouwmeester.core.app:create_app --factory --host 0.0.0.0 --port 8080
