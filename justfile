# Bouwmeester project commands

# Start all services with rebuild
dev:
    docker compose up --build

# Stop all services
down:
    docker compose down

# Open a shell in the backend container
backend-shell:
    docker compose exec backend bash

# Open a psql shell in the database container
db-shell:
    docker compose exec db psql -U bouwmeester

# Run database migrations
migrate:
    docker compose exec backend uv run alembic upgrade head

# Create a new migration
migration NAME:
    docker compose exec backend uv run alembic revision --autogenerate -m "{{ NAME }}"

# Seed the database
seed:
    docker compose exec backend uv run python -m bouwmeester.seed

# Lint the backend code
lint:
    cd backend && uv run ruff check . && uv run ruff format --check .

# Format the backend code
format:
    cd backend && uv run ruff format .

# Run backend tests
test:
    cd backend && uv run pytest
