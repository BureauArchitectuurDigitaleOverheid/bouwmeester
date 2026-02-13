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

**Base URL:** The API backend runs at
`https://component-2.bouwmeester.rijks.app` (production) or
`http://localhost:8000` (local dev). All examples below use `$BASE`
as a placeholder — set it before running:

```bash
BASE=https://component-2.bouwmeester.rijks.app   # production
# BASE=http://localhost:8000                       # local dev
```

### Verify your identity

After authenticating, confirm your agent identity:

```bash
curl -H "Authorization: Bearer bm_..." $BASE/api/auth/me
```

Returns your `PersonDetailResponse` (id, naam, email, is_agent, etc.).
Use this to discover your `person_id` for task assignment and audit logging.

### Rate limiting

Failed API key attempts are tracked per IP address. After 10 failures
within 60 seconds, additional warnings are logged. There is no hard
block, but persistent failures are monitored.

## Error Responses

All errors return JSON with a `detail` field:

```json
{"detail": "Human-readable error message"}
```

Common HTTP status codes:

| Code | Meaning |
|------|---------|
| 401  | Missing or invalid authentication (bad API key or expired session) |
| 403  | Authenticated but not authorized (e.g. not on access whitelist) |
| 404  | Entity not found |
| 409  | Conflict (e.g. duplicate edge between the same two nodes) |
| 422  | Validation error — request body failed Pydantic validation. The `detail` field contains a list of field-level errors |

## Core Concepts

| Concept | Description |
|---------|-------------|
| **CorpusNode** | A node in the policy graph. Types: dossier, doel, instrument, beleidskader, maatregel, politieke_input, probleem, effect, beleidsoptie, bron |
| **Edge** | A typed, directed link between two nodes (e.g. "draagt_bij_aan", "implementeert") |
| **EdgeType** | Defines the relationship type (string ID like "draagt_bij_aan"). See the full list below |
| **Task** | An action item linked to a node, with assignee, priority, deadline |
| **Person** | A user or agent. Agents have `is_agent: true` and use API keys |
| **OrganisatieEenheid** | Organizational unit (Ministerie > DG > Directie > Afdeling > Team) |
| **Tag** | Hierarchical label applied to nodes via NodeTag |
| **NodeStakeholder** | Links a person to a node with a role (eigenaar/betrokken/adviseur) |
| **Notification** | In-app messages and alerts for persons |
| **Activity** | Audit log of all create/update/delete actions |
| **ParlementairItem** | Imported parliamentary items (moties, kamervragen, toezeggingen). These have **suggested edges** that are reviewed by humans via `/api/parlementair/edges/*` — agents should generally not interact with this review workflow |

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
| `bron` | Bron — a source document (see "Bron nodes" section below) |

### Node status

The `status` field on nodes is a **free-text string** (max 50 characters),
not an enum. Common values used in practice: `actief`, `concept`,
`ingetrokken`. You may set any short string value. Default: `actief`.

## Edge Types

These are the built-in relationship types for edges. Retrieve the full
list from `GET /api/edge-types`. Use the `id` value as `edge_type_id`
when creating edges.

| id | label | Description |
|----|-------|-------------|
| `implementeert` | Implementeert | The source node implements the target |
| `draagt_bij_aan` | Draagt bij aan | The source contributes to the target |
| `vloeit_voort_uit` | Vloeit voort uit | The source results from the target |
| `conflicteert_met` | Conflicteert met | The source conflicts with the target |
| `verwijst_naar` | Verwijst naar | The source refers to the target |
| `vereist` | Vereist | The source requires the target |
| `evalueert` | Evalueert | The source evaluates the target |
| `vervangt` | Vervangt | The source replaces the target |
| `onderdeel_van` | Onderdeel van | The source is part of the target |
| `leidt_tot` | Leidt tot | The source leads to the target |
| `adresseert` | Adresseert | The source addresses the target |
| `meet` | Meet | The source measures the target |

New edge types can be created via `POST /api/edge-types`.

## Bron Nodes (Source Documents)

Nodes of type `bron` have additional fields and capabilities:

**Extra fields** (via `bron_detail`):
- `type` — one of: `rapport`, `onderzoek`, `wetgeving`, `advies`, `opinie`, `beleidsnota`, `evaluatie`, `overig`
- `auteur` — author name (string)
- `publicatie_datum` — publication date
- `url` — link to the source (must start with `http://` or `https://`)

**Bron-specific endpoints:**
- `GET /api/nodes/{id}/bron-detail` — get bron metadata
- `PUT /api/nodes/{id}/bron-detail` — update bron metadata

**File attachments** (bijlagen):
- `POST /api/nodes/{id}/bijlage` — upload a file (multipart/form-data)
- `GET /api/nodes/{id}/bijlage` — list attachments
- `GET /api/nodes/{id}/bijlage/{bijlage_id}/download` — download a file
- `DELETE /api/nodes/{id}/bijlage/{bijlage_id}` — delete an attachment

## Common Workflows

### 1. List and read nodes

```bash
# List all nodes (paginated)
curl -H "Authorization: Bearer bm_..." $BASE/api/nodes?limit=20

# Filter by type
curl -H "Authorization: Bearer bm_..." $BASE/api/nodes?node_type=dossier

# Get a single node with its edges
curl -H "Authorization: Bearer bm_..." $BASE/api/nodes/{id}
```

### 2. Create a node

```bash
curl -X POST $BASE/api/nodes \
  -H "Authorization: Bearer bm_..." \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Woningbouwopgave",
    "description": "Dossier over de nationale woningbouwopgave",
    "node_type": "dossier",
    "status": "actief"
  }'
```

### 3. Create an edge between two nodes

```bash
curl -X POST $BASE/api/edges \
  -H "Authorization: Bearer bm_..." \
  -H "Content-Type: application/json" \
  -d '{
    "from_node_id": "<uuid>",
    "to_node_id": "<uuid>",
    "edge_type_id": "draagt_bij_aan",
    "description": "Dit instrument draagt bij aan het doel"
  }'
```

### 4. Create a task on a node

```bash
curl -X POST $BASE/api/tasks \
  -H "Authorization: Bearer bm_..." \
  -H "Content-Type: application/json" \
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
curl -H "Authorization: Bearer bm_..." \
  "$BASE/api/search?q=woningbouw&limit=20"
```

### 6. Get the graph around a node

```bash
# Direct neighbors
curl -H "Authorization: Bearer bm_..." $BASE/api/nodes/{id}/neighbors

# Multi-hop graph (depth 1-5)
curl -H "Authorization: Bearer bm_..." $BASE/api/nodes/{id}/graph?depth=2
```

## Important Conventions

- **UUID primary keys** — all entity IDs are UUIDs
- **Pagination** — use `skip` (offset) and `limit` query params; defaults vary per endpoint
- **Dutch labels** — UI labels and some error messages are in Dutch
- **Task priorities** — `kritiek`, `hoog`, `normaal`, `laag`
- **Task statuses** — `open`, `in_progress`, `done`, `cancelled`
- **Node status** — free-text string, max 50 chars. Common values: `actief`, `concept`, `ingetrokken`
- **Stakeholder roles** — `eigenaar` (owner), `betrokken` (involved), `adviseur` (advisor)
- **Org types** — `ministerie`, `directoraat_generaal`, `directie`, `afdeling`, `team`
- **actor_id query param** — many write endpoints accept `?actor_id=<uuid>` to attribute
  the action to a specific person in the audit log
- **Absence management** — the Person model tracks absences and substitutes,
  but there are no dedicated API routes for this yet. Absence data is visible
  in person detail responses.
- **Parliamentary suggested edges** — `SuggestedEdge` records are proposed
  links from parliamentary imports to corpus nodes. They go through a
  human review workflow (approve/reject/reset) via `/api/parlementair/edges/*`.
  Agents should generally not interact with this review process.

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
