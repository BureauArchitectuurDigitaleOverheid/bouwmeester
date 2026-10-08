# Bouwmeester

A shared workspace for people who make policy in the Dutch government. It keeps the building blocks of policy (problems, goals, measures and how they relate) next to the people and the organisation behind them, and it watches parliament so that nobody has to.

Bouwmeester is built and run by the [Nederlandse Digitale Dienst](https://digitaledienst.overheid.nl). It runs at [bouwmeester.rijks.app](https://bouwmeester.rijks.app), behind a login.

## What it does

- **Corpus.** Dossiers, goals, instruments and measures as a graph, with tasks and owners on every node.
- **Organisation.** The organisational tree, who works where, and who may see or change what.
- **Initiatives.** Leads and updates per initiative, with an optional public page.
- **Kamerstukken.** Follows search terms in new parliamentary documents and posts the ones that matter to a Mattermost channel, with a summary.
- **Debates.** Follows a debate of the Tweede Kamer live in a Mattermost channel: who speaks, what is said, and the questions, motions and commitments that come out of it.

The interface is in Dutch. An introduction for users is in [`docs/introductie.md`](docs/introductie.md).

## Quick start

```bash
just reset-db    # Nuke DB, migrate, seed, start all services
just up          # Start services (if DB already exists)
just dev         # Start with rebuild (foreground, shows logs)
```

The app runs at http://localhost:5173, the API at http://localhost:8000.

Local development has no identity provider. Pick a person in the header to run every request with that person's roles.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- [just](https://github.com/casey/just) (`brew install just`)
- [uv](https://docs.astral.sh/uv/) (`brew install uv`)
- [Node.js](https://nodejs.org/) for frontend development
- [age](https://age-encryption.org/) (`brew install age`) for the encrypted seed data

## Architecture

- **Backend**: FastAPI, SQLAlchemy 2.0 (async), Alembic, PostgreSQL
- **Worker**: background loops in the same image as the API. They import parliamentary documents, keep the Mattermost connection open and follow debates.
- **Frontend**: React, TypeScript, React Query, Vite, with [`@nldd/design-system`](https://github.com/NederlandseDigitaleDienst/design-system)
- **Development**: Docker Compose

More detail is in [`docs/technisch.md`](docs/technisch.md) and [`docs/functioneel.md`](docs/functioneel.md). Setting up a local Mattermost is described in [`docs/mattermost-setup.md`](docs/mattermost-setup.md).

## Tests and checks

```bash
just test             # Backend tests (needs the database: just up)
just lint             # Backend lint and format check (ruff)
just test-frontend    # Frontend tests (vitest)
just typecheck        # Frontend TypeScript check
```

The backend tests run against a real PostgreSQL. Each parallel worker gets a database of its own.

## Deployment

A merge to `main` builds the backend and frontend images, pushes them to `ghcr.io/nederlandsedigitaledienst/bouwmeester` and rolls them out on [ZAD](https://github.com/RijksICTGilde/RIG-Cluster). Migrations run when the backend starts.

A rollout restarts the worker. It picks up where it left off, so a deploy during office hours does not cost alerts.

## Seed data and PII

Person data in the seed script is **not** stored in git as plaintext (AVG/GDPR). Instead:

- `backend/scripts/seed_persons.json` is the plaintext person data. It is **gitignored**.
- `backend/scripts/seed_persons.json.age` is the [age](https://age-encryption.org/)-encrypted version. It is **committed**.

The seed script loads from the JSON file. If the file is missing, it generates placeholder persons so `just reset-db` always works.

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
| `just worker-logs` | Follow the logs of the worker |
| `just db-shell` | Open psql shell |
| `just lint` | Backend lint (ruff) |
| `just test` | Backend tests |
| `just typecheck` | Frontend TypeScript check |
