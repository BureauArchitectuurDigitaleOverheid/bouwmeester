# Bouwmeester

Policy corpus management tool for the Dutch government (BZK). Manages organisational structure, people, policy dossiers, tasks, and their relationships.

## Quick start

```bash
just reset-db    # Nuke DB, migrate, seed, start all services
just up          # Start services (if DB already exists)
just dev         # Start with rebuild (foreground, shows logs)
```

App runs at http://localhost:5173, API at http://localhost:8000.

## Just commands

Run `just` to see all available commands. Key ones:

| Command | What it does |
|---------|-------------|
| `just up` | Start all services in background |
| `just down` | Stop services (keeps data) |
| `just nuke` | Stop + delete all data |
| `just reset-db` | Full reset: nuke, migrate, seed, start |
| `just migrate` | Run Alembic migrations |
| `just seed` | Seed test data |
| `just restart-backend` | Restart backend after code changes |
| `just typecheck` | Frontend TypeScript check |
| `just lint` | Backend lint (ruff) |
| `just logs` | Follow all service logs |
| `just db-shell` | Open psql shell |
| `just worker-logs` | Follow worker service logs |
| `just import-moties` | Manually trigger motie import via API |

## Architecture

- **Backend**: FastAPI + SQLAlchemy 2.0 async + Alembic + PostgreSQL (asyncpg)
- **Frontend**: React + TypeScript + React Query + Tailwind CSS + Vite
- **Infra**: Docker Compose (dev), Kubernetes manifests in `k8s/`
- **Python**: Use `uv` for ALL python operations (never pip/poetry)

## Project structure

```
backend/
  bouwmeester/
    api/routes/       # FastAPI routers (one file per domain)
    models/           # SQLAlchemy 2.0 models
    schema/           # Pydantic v2 schemas
    repositories/     # Database access (no service layer for simple CRUD)
    services/         # Business logic (only where needed)
    migrations/       # Alembic migrations
  scripts/seed.py     # Test data seed script
frontend/
  src/
    api/              # API client functions (apiGet/apiPost/apiPut/apiDelete)
    components/       # React components by domain
    hooks/            # React Query hooks
    pages/            # Page components (route targets)
    types/            # TypeScript types and constants
```

## Backend patterns

- **Models**: `Mapped[type]`, `mapped_column()`, UUID PKs with `server_default=text("gen_random_uuid()")`
- **Schemas**: Pydantic v2, `ConfigDict(from_attributes=True)`, pattern: Base/Create/Update/Response
- **Routes**: Direct repo usage with `Depends(get_db)`, no service layer for simple CRUD
- **Registries**: New models → `models/__init__.py`, new schemas → `schema/__init__.py`, new routers → `api/routes/__init__.py`

### Adding a new model

1. Create model in `models/new_thing.py`
2. Import in `models/__init__.py`
3. Create schemas in `schema/new_thing.py` (Base, Create, Update, Response)
4. Import in `schema/__init__.py`
5. Create repository in `repositories/new_thing.py`
6. Create router in `api/routes/new_thing.py`
7. Register router in `api/routes/__init__.py`
8. Generate migration: `just migration "add new thing"`

## Frontend patterns

- **Path alias**: `@/` maps to `src/`
- **API helpers**: `apiGet`, `apiPost`, `apiPut`, `apiDelete` in `api/client.ts`
- **Hooks**: React Query `useQuery`/`useMutation` with `queryKey` invalidation
- **Components**: `CreatableSelect` for all dropdowns (select + create inline)
- **Layout**: `Header.tsx` renders page title from `pageTitles` map — pages should NOT have their own `<h1>`
- **Sidebar**: Nav items defined in `components/layout/Sidebar.tsx`
- **Route definitions**: `App.tsx`

### Adding a new page

1. Create page component in `pages/NewPage.tsx` (no `<h1>`, Header handles it)
2. Add route in `App.tsx`
3. Add nav item in `Sidebar.tsx`
4. Add title in `Header.tsx` `pageTitles` map

## UI conventions

- Dutch labels throughout (Bewerken, Toevoegen, Verwijderen, etc.)
- Organisatie types: Ministerie, Directoraat-Generaal, Directie, Afdeling, Team
- Role labels defined in `ROL_LABELS` (`types/index.ts`) for display
- Node types: Dossier, Doel, Instrument, Beleidskader, Maatregel, Politieke Input
- Color maps (`TYPE_BADGE_COLORS`, `NODE_TYPE_COLORS`, `TASK_PRIORITY_COLORS`) in types

## Key data relationships

```
Person
├── Task (assignee_id)
├── NodeStakeholder (eigenaar/betrokken/adviseur on corpus nodes)
├── OrganisatieEenheid (member via organisatie_eenheid_id)
├── OrganisatieEenheid (manager via manager_id)
├── Activity (actor_id)
├── Notification (person_id)
└── Absence (person_id / substitute_id)

CorpusNode (dossier/doel/instrument/beleidskader/maatregel/politieke_input/probleem/effect/beleidsoptie)
├── Edge (from_node_id / to_node_id, typed via EdgeType)
├── Task (node_id)
├── NodeStakeholder (node_id)
└── NodeTag (node_id → Tag, hierarchical tagging)

Tag (hierarchical, parent_id self-ref)
└── NodeTag (many-to-many with CorpusNode)

MotieImport (tracks imported TK/EK moties)
├── SuggestedEdge (proposed edges to corpus nodes, pending review)
└── CorpusNode (corpus_node_id, the created politieke_input node)
```

## Database

- PostgreSQL 16, connection via Docker Compose on `localhost:5432`
- Credentials: `bouwmeester` / `bouwmeester` / `bouwmeester` (user/password/db)
- Migrations run locally via `uv` (not inside Docker), connecting to localhost
- DB may not always be running — use `just up` or `docker compose up -d db` first
