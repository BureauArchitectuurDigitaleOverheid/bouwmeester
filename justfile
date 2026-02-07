# Bouwmeester (Bado-Tool) project commands

# Default: list all available recipes
default:
    @just --list

# ---------------------------------------------------------------------------
# Development lifecycle
# ---------------------------------------------------------------------------

# Start all services (db + backend + frontend) with rebuild
dev:
    docker compose up --build

# Start all services in background
up:
    docker compose up -d

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
    docker compose up -d db
    @echo "Wachten op database..."
    @sleep 3
    cd backend && uv run alembic upgrade head
    cd backend && uv run python scripts/seed.py
    docker compose up -d backend frontend
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

# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

# TypeScript type check (no emit)
typecheck:
    cd frontend && npx tsc --noEmit

# Install frontend dependencies
install-frontend:
    cd frontend && npm install
