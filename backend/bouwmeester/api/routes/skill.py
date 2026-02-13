"""Skill endpoint — returns a Markdown guide for LLM agent consumption."""

# ruff: noqa: E501 — Markdown content has long table rows by design.

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["skill"])

SKILL_MD = """\
# Bouwmeester API — Agent Skill Guide

Bouwmeester is a policy corpus management tool for the Dutch government
(Ministry of the Interior / BZK). It manages policy dossiers, goals,
instruments, measures, and their relationships as a directed graph.

## Authentication

All API endpoints (except `/api/skill.md`, `/api/auth/*`, `/api/health/*`)
require authentication.

**For agents**, use a `bm_`-prefixed API key in the `Authorization` header:

```
Authorization: Bearer bm_abc123...
```

API keys are created when an agent Person is created (POST /api/people with
`is_agent: true`, admin only). The plaintext key is returned once on creation.
Keys can be rotated via POST `/api/people/{id}/rotate-api-key`.

## Core Concepts

| Concept | Description |
|---------|-------------|
| **CorpusNode** | A node in the policy graph. Types: dossier, doel, instrument, beleidskader, maatregel, politieke_input, probleem, effect, beleidsoptie, bron |
| **Edge** | A typed, directed link between two nodes (e.g. "draagt_bij_aan", "implementeert") |
| **EdgeType** | Defines the relationship type (string ID like "draagt_bij_aan") |
| **Task** | An action item linked to a node, with assignee, priority, deadline |
| **Person** | A user or agent. Agents have `is_agent: true` and use API keys |
| **OrganisatieEenheid** | Organizational unit (Ministerie > DG > Directie > Afdeling > Team) |
| **Tag** | Hierarchical label applied to nodes via NodeTag |
| **NodeStakeholder** | Links a person to a node with a role (eigenaar/betrokken/adviseur) |
| **Notification** | In-app messages and alerts for persons |
| **Activity** | Audit log of all create/update/delete actions |
| **ParlementairItem** | Imported parliamentary items (moties, kamervragen, toezeggingen) |

## Node Types (Dutch)

| Type | Description |
|------|-------------|
| `dossier` | Beleidsdossier — a policy dossier grouping related items |
| `doel` | Beleidsdoel — a policy goal |
| `instrument` | Beleidsinstrument — a policy instrument |
| `beleidskader` | Beleidskader — a policy framework |
| `maatregel` | Maatregel — a concrete measure |
| `politieke_input` | Politieke input — parliamentary items (moties, kamervragen) |
| `probleem` | Probleem — a policy problem |
| `effect` | Effect — an expected or measured effect |
| `beleidsoptie` | Beleidsoptie — a policy option |
| `bron` | Bron — a source document (can have file attachments) |

## Common Workflows

### 1. List and read nodes

```bash
# List all nodes (paginated)
curl -H "Authorization: Bearer bm_..." http://localhost:8000/api/nodes?limit=20

# Filter by type
curl -H "Authorization: Bearer bm_..." http://localhost:8000/api/nodes?node_type=dossier

# Get a single node with its edges
curl -H "Authorization: Bearer bm_..." http://localhost:8000/api/nodes/{id}
```

### 2. Create a node

```bash
curl -X POST http://localhost:8000/api/nodes \\
  -H "Authorization: Bearer bm_..." \\
  -H "Content-Type: application/json" \\
  -d '{
    "title": "Woningbouwopgave",
    "description": "Dossier over de nationale woningbouwopgave",
    "node_type": "dossier",
    "status": "actief"
  }'
```

### 3. Create an edge between two nodes

```bash
curl -X POST http://localhost:8000/api/edges \\
  -H "Authorization: Bearer bm_..." \\
  -H "Content-Type: application/json" \\
  -d '{
    "from_node_id": "<uuid>",
    "to_node_id": "<uuid>",
    "edge_type_id": "draagt_bij_aan",
    "description": "Dit instrument draagt bij aan het doel"
  }'
```

### 4. Create a task on a node

```bash
curl -X POST http://localhost:8000/api/tasks \\
  -H "Authorization: Bearer bm_..." \\
  -H "Content-Type: application/json" \\
  -d '{
    "title": "Analyseer impact nieuwe wetgeving",
    "node_id": "<uuid>",
    "assignee_id": "<uuid>",
    "priority": "hoog",
    "status": "open"
  }'
```

### 5. Search across all entities

```bash
curl -H "Authorization: Bearer bm_..." \\
  "http://localhost:8000/api/search?q=woningbouw&limit=20"
```

### 6. Get the graph around a node

```bash
# Direct neighbors
curl -H "Authorization: Bearer bm_..." http://localhost:8000/api/nodes/{id}/neighbors

# Multi-hop graph (depth 1-5)
curl -H "Authorization: Bearer bm_..." http://localhost:8000/api/nodes/{id}/graph?depth=2
```

## Important Conventions

- **UUID primary keys** — all entity IDs are UUIDs
- **Pagination** — use `skip` (offset) and `limit` query params; defaults vary per endpoint
- **Dutch labels** — UI labels and some error messages are in Dutch
- **Task priorities** — `kritiek`, `hoog`, `normaal`, `laag`
- **Task statuses** — `open`, `in_progress`, `done`, `cancelled`
- **Node statuses** — typically `actief`, `concept`, `ingetrokken`
- **Stakeholder roles** — `eigenaar` (owner), `betrokken` (involved), `adviseur` (advisor)
- **Org types** — `ministerie`, `directoraat_generaal`, `directie`, `afdeling`, `team`
- **actor_id query param** — many write endpoints accept `?actor_id=<uuid>` to attribute
  the action to a specific person in the audit log

## Full API Reference

- **OpenAPI spec**: `GET /openapi.json`
- **Interactive docs**: `GET /docs` (Swagger UI)
- **Alternative docs**: `GET /redoc` (ReDoc)

Each endpoint has a docstring visible in the OpenAPI spec describing its
purpose and key behavior.
"""


@router.get("/skill.md", response_class=PlainTextResponse)
async def get_skill_document() -> str:
    """Return a Markdown guide describing the API for LLM agent consumption."""
    return SKILL_MD
