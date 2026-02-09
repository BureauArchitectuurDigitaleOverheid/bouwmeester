# Bouwmeester

Policy corpus management tool for the Dutch government (BZK). Manages organisational structure, people, policy dossiers, tasks, and their relationships.

## Quick start

```bash
just reset-db    # Nuke DB, migrate, seed, start all services
just up          # Start services (if DB already exists)
just dev         # Start with rebuild (foreground, shows logs)
```

App runs at http://localhost:5173, API at http://localhost:8000.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- [just](https://github.com/casey/just) (`brew install just`)
- [uv](https://docs.astral.sh/uv/) (`brew install uv`)
- [Node.js](https://nodejs.org/) (for frontend development)
- [age](https://age-encryption.org/) (`brew install age`) — for seed data encryption

## Architecture

- **Backend**: FastAPI + SQLAlchemy 2.0 async + Alembic + PostgreSQL
- **Frontend**: React + TypeScript + React Query + Tailwind CSS + Vite
- **Infra**: Docker Compose (dev), Kubernetes manifests in `k8s/`

## Seed data and PII

Person data in the seed script is **not** stored in git as plaintext (AVG/GDPR). Instead:

- `backend/scripts/seed_persons.json` — plaintext person data, **gitignored**
- `backend/scripts/seed_persons.json.age` — [age](https://age-encryption.org/)-encrypted version, **committed**

The seed script loads from the JSON file. If missing, it generates placeholder persons so `just reset-db` always works.

### First-time setup (seed data access)

```bash
# 1. Generate your age key
brew install age
mkdir -p ~/.age
age-keygen -o ~/.age/key.txt
# Send the printed public key (age1...) to a team member

# 2. After your key is added to the justfile by a team member:
just decrypt-seed

# 3. Now reset-db uses real person data:
just reset-db
```

### Editing person data

```bash
just decrypt-seed              # .age → .json
# Edit backend/scripts/seed_persons.json
just encrypt-seed              # .json → .age
git add backend/scripts/seed_persons.json.age
git commit -m "Update seed person data"
```

## Available commands

Run `just` to see all commands. Key ones:

| Command | What it does |
|---------|-------------|
| `just up` | Start all services in background |
| `just down` | Stop services (keeps data) |
| `just nuke` | Stop + delete all data |
| `just reset-db` | Full reset: nuke, migrate, seed, start |
| `just migrate` | Run Alembic migrations |
| `just seed` | Seed test data |
| `just decrypt-seed` | Decrypt seed person data |
| `just encrypt-seed` | Encrypt seed person data |
| `just logs` | Follow all service logs |
| `just db-shell` | Open psql shell |
| `just lint` | Backend lint (ruff) |
| `just typecheck` | Frontend TypeScript check |
