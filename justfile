# Bouwmeester project commands

# Default: list all available recipes
default:
    @just --list

# ---------------------------------------------------------------------------
# Development lifecycle
# ---------------------------------------------------------------------------

# Start all services (db + backend + frontend) with rebuild
dev:
    docker compose up --build

# Start all services in background (with rebuild)
up:
    docker compose up -d --build

# Stop all services (keeps data)
down:
    docker compose down

# Stop all services and DELETE all data (volumes)
nuke:
    docker compose down -v

# Restart backend (picks up code changes without full rebuild)
restart-backend:
    docker compose restart backend

# Restart all services
restart:
    docker compose restart

# View logs (all services, follow mode)
logs:
    docker compose logs -f

# View backend logs only
logs-backend:
    docker compose logs -f backend

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

# Run database migrations
migrate:
    cd backend && uv run alembic upgrade head

# Create a new migration (auto-generated from model changes)
migration NAME:
    cd backend && uv run alembic revision --autogenerate -m "{{ NAME }}"

# Seed the database with test data
seed:
    cd backend && uv run python scripts/seed.py

# Full database reset: nuke → start db → wait → migrate → seed → start services
reset-db:
    docker compose down -v
    docker compose up -d --build db
    @echo "Wachten op database..."
    @sleep 3
    cd backend && uv run alembic upgrade head
    cd backend && uv run python scripts/seed.py
    docker compose up -d --build backend frontend
    @echo "Klaar! Alle services draaien."

# Open a psql shell in the database container
db-shell:
    docker compose exec db psql -U bouwmeester

# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------

# Open a shell in the backend container
backend-shell:
    docker compose exec backend bash

# Lint the backend code (ruff check + format check)
lint:
    cd backend && uv run ruff check . && uv run ruff format --check .

# Format the backend code
format:
    cd backend && uv run ruff format .

# Run backend tests
test:
    cd backend && uv run pytest

# Run backend tests with coverage report
test-cov:
    cd backend && uv run pytest -n auto --cov --cov-report=term-missing

# Run backend tests for CI (with coverage XML output)
test-ci:
    cd backend && uv run pytest -n auto --cov --cov-report=xml --cov-fail-under=80

# Run frontend tests
test-frontend:
    cd frontend && npx vitest run

# Run frontend tests with coverage
test-frontend-cov:
    cd frontend && npx vitest run --coverage

# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

# TypeScript type check (no emit)
typecheck:
    cd frontend && npx tsc --noEmit

# Install frontend dependencies
install-frontend:
    cd frontend && npm install

# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

# View worker logs
worker-logs:
    docker compose logs -f worker

# Manually trigger parliamentary item import (via API, all enabled types)
import-parlementair:
    curl -X POST http://localhost:8000/api/parlementair/imports/trigger

# Import specific type (motie, kamervraag, toezegging)
import-type TYPE:
    curl -X POST "http://localhost:8000/api/parlementair/imports/trigger?types={{ TYPE }}"

# Backward-compatible alias
import-moties: import-parlementair

# ---------------------------------------------------------------------------
# Mattermost
# ---------------------------------------------------------------------------

# Start services including local Mattermost
mattermost-up:
    docker compose --profile mattermost up -d --build

# View Mattermost logs
mattermost-logs:
    docker compose logs -f mattermost

# ---------------------------------------------------------------------------
# Database backup / restore (via API)
# ---------------------------------------------------------------------------

# Export database via API (downloads to current directory)
db-export:
    curl -sS -o bouwmeester-backup.tar.gz http://localhost:8000/api/admin/database/export
    @echo "Downloaded → bouwmeester-backup.tar.gz"

# Import database via API (provide backup file as argument)
db-import FILE:
    curl -sS -X POST -F "file=@{{ FILE }}" http://localhost:8000/api/admin/database/import | python3 -m json.tool
    @echo "Import complete."

# ---------------------------------------------------------------------------
# Age encryption (shared recipes)
# ---------------------------------------------------------------------------

# Decrypt a JSON file from the committed .age file
_decrypt file:
    age -d -i ~/.age/key.txt -o backend/scripts/{{file}} backend/scripts/{{file}}.age
    @echo "Decrypted → backend/scripts/{{file}}"

# Encrypt a JSON file for committing (recipients from age-recipients.txt)
_encrypt file:
    @test -f age-recipients.txt || { echo "Error: age-recipients.txt not found"; exit 1; }
    age $(grep -v '^#' age-recipients.txt | grep -v '^\s*$' | sed 's/^/-r /') \
        -o backend/scripts/{{file}}.age \
        backend/scripts/{{file}}
    @echo "Encrypted → backend/scripts/{{file}}.age"

# Convenience aliases
decrypt-seed: (_decrypt "seed_persons.json")
encrypt-seed: (_encrypt "seed_persons.json")
decrypt-admins: (_decrypt "admin_emails.json")
encrypt-admins: (_encrypt "admin_emails.json")
