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
| **Task** | An action item linked to a node, with assignee, priority, deadline. Supports subtask hierarchy via `parent_id` |
| **Person** | A user or agent. Agents have `is_agent: true` and use API keys |
| **OrganisatieEenheid** | Organizational unit (ministerie > directoraat_generaal > directie > dienst > afdeling > cluster/bureau > team) |
| **Tag** | Hierarchical label applied to nodes via NodeTag |
| **NodeStakeholder** | Links a person to a node with a role (eigenaar/betrokken/adviseur/indiener) |
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

### Type-specific detail fields

Each node type has an associated detail table in the database with
type-specific fields. Currently **only `bron`** has dedicated API
endpoints (`GET/PUT /nodes/{id}/bron-detail`). The other detail tables
exist in the database but are **not yet exposed via API**. They are
listed here so agents know what data exists:

| node_type | Detail fields (type — enum values) | API |
|-----------|-----------------------------------|-----|
| `dossier` | `fase` (str — `verkenning` \\| `beleidsvorming` \\| `uitvoering` \\| `evaluatie`), `eigenaar` (str?), `deadline` (date?), `prioriteit` (str — `laag` \\| `normaal` \\| `hoog` \\| `kritiek`, default `normaal`) | none yet |
| `doel` | `type` (str — `politiek` \\| `organisatorisch` \\| `operationeel`), `bron` (str?), `meetbaar` (bool, default false), `streefwaarde` (str?) | none yet |
| `instrument` | `type` (str — `wetgeving` \\| `subsidie` \\| `voorlichting` \\| `handhaving` \\| `overig`), `rechtsgrondslag` (str?) | none yet |
| `beleidskader` | `scope` (str — `nationaal` \\| `eu` \\| `internationaal`), `geldig_van` (date?), `geldig_tot` (date?) | none yet |
| `maatregel` | `kosten_indicatie` (str?), `verwacht_effect` (str?), `uitvoerder` (str?) | none yet |
| `beleidsoptie` | `status` (str — `verkennend` \\| `voorgesteld` \\| `gekozen` \\| `afgewezen`, default `verkennend`), `kosten_indicatie` (str?), `verwacht_effect` (str?), `risico` (str?) | none yet |
| `probleem` | `urgentie` (str — `laag` \\| `normaal` \\| `hoog` \\| `kritiek`, default `normaal`), `bron` (str?), `impact_beschrijving` (str?) | none yet |
| `effect` | `type` (str — `output` \\| `outcome` \\| `impact`), `indicator` (str?), `streefwaarde` (str?), `meetbaar` (bool, default false) | none yet |
| `politieke_input` | `type` (str — `coalitieakkoord` \\| `motie` \\| `kamerbrief` \\| `toezegging` \\| `amendement` \\| `kamervraag` \\| `commissiedebat` \\| `schriftelijk_overleg` \\| `interpellatie`), `referentie` (str?), `datum` (date?), `status` (str — `open` \\| `in_behandeling` \\| `afgedaan`, default `open`) | none yet |
| `bron` | `type` (str — `rapport` \\| `onderzoek` \\| `wetgeving` \\| `advies` \\| `opinie` \\| `beleidsnota` \\| `evaluatie` \\| `overig`), `auteur` (str?), `publicatie_datum` (date?), `url` (str?) | `GET/PUT /nodes/{id}/bron-detail` |

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

## Response Shapes

### CorpusNodeResponse (list item)

```json
{
  "id": "uuid",
  "title": "string",
  "description": "string | null",
  "node_type": "dossier",
  "status": "actief",
  "geldig_van": "2025-01-01 | null",
  "geldig_tot": "null",
  "edge_count": 5,
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-01-01T00:00:00Z | null"
}
```

### CorpusNodeWithEdges (single GET /nodes/{id})

Extends CorpusNodeResponse with edge arrays:

```json
{
  "id": "uuid",
  "title": "string",
  "description": "string | null",
  "node_type": "dossier",
  "status": "actief",
  "geldig_van": "2025-01-01 | null",
  "geldig_tot": "null",
  "edge_count": 2,
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "null",
  "edges_from": [
    {"id": "uuid", "from_node_id": "uuid", "to_node_id": "uuid", "edge_type_id": "draagt_bij_aan", "weight": 1.0, "description": "string | null", "created_at": "2025-01-01T00:00:00Z"}
  ],
  "edges_to": []
}
```

### EdgeResponse

```json
{
  "id": "uuid",
  "from_node_id": "uuid",
  "to_node_id": "uuid",
  "edge_type_id": "draagt_bij_aan",
  "weight": 1.0,
  "description": "string | null",
  "created_at": "2025-01-01T00:00:00Z"
}
```

### EdgeWithNodes (returned by GET /edges)

Extends EdgeResponse with full node objects:

```json
{
  "id": "uuid",
  "from_node_id": "uuid",
  "to_node_id": "uuid",
  "edge_type_id": "draagt_bij_aan",
  "weight": 1.0,
  "description": "string | null",
  "created_at": "2025-01-01T00:00:00Z",
  "from_node": {"id": "uuid", "title": "...", "node_type": "dossier", "...": "..."},
  "to_node": {"id": "uuid", "title": "...", "node_type": "doel", "...": "..."}
}
```

### TaskResponse

```json
{
  "id": "uuid",
  "title": "string",
  "description": "string | null",
  "node_id": "uuid",
  "node": {"id": "uuid", "title": "string", "node_type": "dossier"} | null,
  "assignee_id": "uuid | null",
  "assignee": {"id": "uuid", "naam": "string", "is_agent": false} | null,
  "organisatie_eenheid_id": "uuid | null",
  "organisatie_eenheid": {"id": "uuid", "naam": "string", "type": "directie"} | null,
  "parent_id": "uuid | null",
  "parlementair_item_id": "uuid | null",
  "subtasks": [
    {"id": "uuid", "title": "string", "status": "open", "priority": "normaal", "assignee": null, "due_date": null}
  ],
  "status": "open",
  "priority": "normaal",
  "due_date": "2025-06-01 | null",
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "null"
}
```

### GraphNeighborsResponse (GET /nodes/{id}/neighbors)

```json
{
  "node": {"id": "uuid", "title": "...", "node_type": "dossier", "...": "..."},
  "neighbors": [
    {
      "node": {"id": "uuid", "title": "...", "node_type": "doel", "...": "..."},
      "edge": {"id": "uuid", "from_node_id": "uuid", "to_node_id": "uuid", "edge_type_id": "draagt_bij_aan", "weight": 1.0, "description": null, "created_at": "2025-01-01T00:00:00Z"}
    }
  ]
}
```

### GraphViewResponse (GET /nodes/{id}/graph, GET /graph/search)

```json
{
  "nodes": [{"id": "uuid", "title": "...", "node_type": "dossier", "...": "..."}],
  "edges": [{"id": "uuid", "from_node_id": "uuid", "to_node_id": "uuid", "edge_type_id": "draagt_bij_aan", "weight": 1.0, "description": null, "created_at": "2025-01-01T00:00:00Z"}]
}
```

### SearchResponse (GET /search)

```json
{
  "results": [
    {
      "id": "uuid",
      "result_type": "corpus_node",
      "title": "Woningbouwopgave",
      "subtitle": "dossier | null",
      "description": "string | null",
      "score": 0.95,
      "highlights": ["matched text fragment"] | null,
      "url": "/nodes/uuid"
    }
  ],
  "total": 42,
  "query": "woningbouw"
}
```

`result_type` is one of: `corpus_node`, `task`, `person`, `organisatie_eenheid`, `parlementair_item`, `tag`.

### NotificationResponse

```json
{
  "id": "uuid",
  "person_id": "uuid",
  "type": "task_assigned",
  "title": "string",
  "message": "string | null",
  "sender_id": "uuid | null",
  "sender_name": "string | null",
  "related_node_id": "uuid | null",
  "related_task_id": "uuid | null",
  "parent_id": "uuid | null",
  "thread_id": "uuid | null",
  "is_read": false,
  "reply_count": 0,
  "last_activity_at": "2025-01-01T00:00:00Z | null",
  "last_message": "string | null",
  "created_at": "2025-01-01T00:00:00Z"
}
```

`type` is one of: `task_assigned`, `task_overdue`, `task_completed`, `task_reassigned`, `node_updated`, `edge_created`, `coverage_needed`, `stakeholder_added`, `stakeholder_role_changed`, `politieke_input_imported`, `direct_message`, `agent_prompt`, `mention`, `access_request`.

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
curl -H "Authorization: Bearer bm_..." "$BASE/api/nodes?limit=20"

# Filter by type
curl -H "Authorization: Bearer bm_..." "$BASE/api/nodes?node_type=dossier"

# Get a single node with its edges
curl -H "Authorization: Bearer bm_..." "$BASE/api/nodes/{id}"
```

### 2. Create a node

```bash
curl -X POST $BASE/api/nodes \\
  -H "Authorization: Bearer bm_..." \\
  -H "Content-Type: application/json" \\
  -d '{
    "title": "Woningbouwopgave",
    "description": "Dossier over de nationale woningbouwopgave",
    "node_type": "dossier",
    "status": "actief"
  }'
```

### 3. Update a node

```bash
curl -X PUT $BASE/api/nodes/{id}?actor_id={your_person_id} \\
  -H "Authorization: Bearer bm_..." \\
  -H "Content-Type: application/json" \\
  -d '{
    "title": "Woningbouwopgave 2025",
    "status": "concept"
  }'
```

Only include the fields you want to change. Omitted fields are left unchanged.

### 4. Delete a node

```bash
curl -X DELETE "$BASE/api/nodes/{id}?actor_id={your_person_id}" \\
  -H "Authorization: Bearer bm_..."
```

Returns `204 No Content`. See "Delete Cascade Behavior" below for what gets cleaned up.

### 5. Create an edge between two nodes

```bash
curl -X POST $BASE/api/edges \\
  -H "Authorization: Bearer bm_..." \\
  -H "Content-Type: application/json" \\
  -d '{
    "from_node_id": "<uuid>",
    "to_node_id": "<uuid>",
    "edge_type_id": "draagt_bij_aan",
    "description": "Dit instrument draagt bij aan het doel"
  }'
```

### 6. Update an edge

```bash
curl -X PUT $BASE/api/edges/{id}?actor_id={your_person_id} \\
  -H "Authorization: Bearer bm_..." \\
  -H "Content-Type: application/json" \\
  -d '{
    "weight": 2.0,
    "description": "Updated relationship description"
  }'
```

Updatable fields: `weight`, `description`, `edge_type_id`.

### 7. Delete an edge

```bash
curl -X DELETE "$BASE/api/edges/{id}?actor_id={your_person_id}" \\
  -H "Authorization: Bearer bm_..."
```

Returns `204 No Content`.

### 8. Create a task on a node

```bash
curl -X POST $BASE/api/tasks \\
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

Tasks support subtask hierarchy. Set `parent_id` to nest a task under another:

```bash
curl -X POST $BASE/api/tasks \\
  -H "Authorization: Bearer bm_..." \\
  -H "Content-Type: application/json" \\
  -d '{
    "title": "Deeltaak: specifiek onderdeel",
    "node_id": "<uuid>",
    "parent_id": "<parent_task_uuid>",
    "priority": "normaal",
    "status": "open"
  }'
```

Get subtasks of a task: `GET /api/tasks/{id}/subtasks`

### 9. Update a task

```bash
curl -X PUT $BASE/api/tasks/{id}?actor_id={your_person_id} \\
  -H "Authorization: Bearer bm_..." \\
  -H "Content-Type: application/json" \\
  -d '{
    "status": "done",
    "priority": "normaal"
  }'
```

Changing `assignee_id` or `organisatie_eenheid_id` triggers notifications.
Completing a task (`status: "done"`) notifies the original assigner.

### 10. Delete a task

```bash
curl -X DELETE "$BASE/api/tasks/{id}?actor_id={your_person_id}" \\
  -H "Authorization: Bearer bm_..."
```

Returns `204 No Content`. Subtasks are cascade-deleted.

### 11. Manage stakeholders on a node

```bash
# List stakeholders
curl -H "Authorization: Bearer bm_..." "$BASE/api/nodes/{id}/stakeholders"

# Add a stakeholder (rol: eigenaar, betrokken, adviseur, or indiener)
curl -X POST "$BASE/api/nodes/{id}/stakeholders?actor_id={your_person_id}" \\
  -H "Authorization: Bearer bm_..." \\
  -H "Content-Type: application/json" \\
  -d '{"person_id": "<uuid>", "rol": "eigenaar"}'

# Update stakeholder role
curl -X PUT "$BASE/api/nodes/{id}/stakeholders/{stakeholder_id}?actor_id={your_person_id}" \\
  -H "Authorization: Bearer bm_..." \\
  -H "Content-Type: application/json" \\
  -d '{"rol": "adviseur"}'

# Remove a stakeholder
curl -X DELETE "$BASE/api/nodes/{id}/stakeholders/{stakeholder_id}?actor_id={your_person_id}" \\
  -H "Authorization: Bearer bm_..."
```

### 12. Manage tags on a node

```bash
# List tags on a node
curl -H "Authorization: Bearer bm_..." "$BASE/api/nodes/{id}/tags"

# Add an existing tag by ID
curl -X POST "$BASE/api/nodes/{id}/tags?actor_id={your_person_id}" \\
  -H "Authorization: Bearer bm_..." \\
  -H "Content-Type: application/json" \\
  -d '{"tag_id": "<uuid>"}'

# Add a tag by name (creates the tag if it does not exist)
curl -X POST "$BASE/api/nodes/{id}/tags?actor_id={your_person_id}" \\
  -H "Authorization: Bearer bm_..." \\
  -H "Content-Type: application/json" \\
  -d '{"tag_name": "klimaat"}'

# Remove a tag from a node
curl -X DELETE "$BASE/api/nodes/{id}/tags/{tag_id}?actor_id={your_person_id}" \\
  -H "Authorization: Bearer bm_..."
```

**Tag management endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/tags` | List all tags (flat) |
| GET | `/api/tags/tree` | Tags as hierarchical tree |
| GET | `/api/tags/search?q=klim` | Search tags by name |
| POST | `/api/tags` | Create a new tag (`{name, parent_id?, description?}`) |
| GET | `/api/tags/{tag_id}` | Get single tag |
| PUT | `/api/tags/{tag_id}` | Update tag name/parent/description |
| DELETE | `/api/tags/{tag_id}` | Delete tag (cascades to children and node-tag links) |

### 13. Search across all entities

```bash
curl -H "Authorization: Bearer bm_..." \\
  "$BASE/api/search?q=woningbouw&limit=20"
```

Returns a `SearchResponse` (see Response Shapes). You can filter by type:

```bash
curl -H "Authorization: Bearer bm_..." \\
  "$BASE/api/search?q=woningbouw&result_types=corpus_node&result_types=task"
```

Valid `result_types`: `corpus_node`, `task`, `person`, `organisatie_eenheid`, `parlementair_item`, `tag`.

### 14. Graph views

```bash
# Direct neighbors of a node
curl -H "Authorization: Bearer bm_..." "$BASE/api/nodes/{id}/neighbors"

# Multi-hop subgraph (depth 1-5)
curl -H "Authorization: Bearer bm_..." "$BASE/api/nodes/{id}/graph?depth=2"

# Filtered full graph (by node types and/or edge types)
curl -H "Authorization: Bearer bm_..." \\
  "$BASE/api/graph/search?node_types=dossier&node_types=doel&edge_types=draagt_bij_aan"

# Shortest path between two nodes
curl -H "Authorization: Bearer bm_..." \\
  "$BASE/api/graph/path?from_id={uuid}&to_id={uuid}&max_depth=10"
```

`GET /graph/search` returns a `GraphViewResponse` (`{nodes, edges}`).
`GET /graph/path` also returns a `GraphViewResponse` containing only the
nodes and edges along the shortest path (empty if no path found within
`max_depth`, default 10, max 50).

### 15. Notifications

```bash
# List notifications for a person
curl -H "Authorization: Bearer bm_..." \\
  "$BASE/api/notifications?person_id={uuid}&unread_only=true&limit=50"

# Get unread count
curl -H "Authorization: Bearer bm_..." \\
  "$BASE/api/notifications/count?person_id={uuid}"
# Returns: {"count": 5}

# Mark a single notification as read
curl -X PUT "$BASE/api/notifications/{id}/read" \\
  -H "Authorization: Bearer bm_..."

# Mark all notifications as read
curl -X PUT "$BASE/api/notifications/read-all?person_id={uuid}" \\
  -H "Authorization: Bearer bm_..."
# Returns: {"marked_read": 12}

# Send a direct message to a person
curl -X POST $BASE/api/notifications/send \\
  -H "Authorization: Bearer bm_..." \\
  -H "Content-Type: application/json" \\
  -d '{
    "person_id": "<recipient_uuid>",
    "sender_id": "<your_person_id>",
    "message": "Hoi, kun je deze taak oppakken?"
  }'

# Reply to a notification thread
curl -X POST $BASE/api/notifications/{id}/reply \\
  -H "Authorization: Bearer bm_..." \\
  -H "Content-Type: application/json" \\
  -d '{
    "sender_id": "<your_person_id>",
    "message": "Ja, ik pak het op."
  }'

# Get all replies in a thread
curl -H "Authorization: Bearer bm_..." "$BASE/api/notifications/{id}/replies"

# Dashboard stats (corpus node count, open/overdue tasks)
curl -H "Authorization: Bearer bm_..." \\
  "$BASE/api/notifications/dashboard-stats?person_id={uuid}"
```

## Delete Cascade Behavior

Understanding what happens when entities are deleted:

| Deleted entity | Cascaded deletes | Fields set to null |
|---------------|-----------------|-------------------|
| **CorpusNode** | edges (from + to), tasks, stakeholders, node-tags, title history, status history, bron detail + file attachments | — |
| **Edge** | nothing | — |
| **EdgeType** | **RESTRICTED** — cannot delete if any edges reference it (returns 409/500) | — |
| **Task** | subtasks (via `parent_id` cascade) | — |
| **Person** | stakeholder links, emails, phones, org placements, notifications | tasks: `assignee_id` → null |
| **Tag** | children tags, node-tag links | — |
| **Notification** | reply notifications (via `parent_id` / `thread_id` cascade) | — |
| **OrganisatieEenheid** | **RESTRICTED** on children — cannot delete if sub-units exist. Cascades: placements, name records, parent records, manager records | manager tasks/persons: set to null |

## Important Conventions

- **UUID primary keys** — all entity IDs are UUIDs
- **Pagination** — use `skip` (offset) and `limit` query params. List endpoints return a **plain JSON array** (not wrapped in an envelope). There is no `total` or `has_more` field. To paginate, request with `skip` + `limit` and stop when fewer results than `limit` are returned. The `GET /search` endpoint is the exception — it returns `{results, total, query}`
- **Dutch labels** — UI labels and some error messages are in Dutch
- **Task priorities** — `kritiek`, `hoog`, `normaal`, `laag`
- **Task statuses** — `open`, `in_progress`, `done`, `cancelled`
- **Task subtasks** — tasks support a `parent_id` field for subtask hierarchy. Use `GET /tasks/{id}/subtasks` to list children. Deleting a parent cascades to subtasks
- **Node status** — free-text string, max 50 chars. Common values: `actief`, `concept`, `ingetrokken`
- **Stakeholder roles** — `eigenaar` (owner), `betrokken` (involved), `adviseur` (advisor), `indiener` (submitter)
- **Org types** — `ministerie`, `directoraat_generaal`, `directie`, `dienst`, `afdeling`, `cluster`, `bureau`, `team`
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

- **OpenAPI spec**: `GET /api/openapi.json`
- **Interactive docs**: `GET /api/docs` (Swagger UI)
- **Alternative docs**: `GET /api/redoc` (ReDoc)

Each endpoint has a docstring visible in the OpenAPI spec describing its
purpose and key behavior.
"""


@router.get("/skill.md", response_class=PlainTextResponse)
async def get_skill_document() -> str:
    """Return a Markdown guide describing the API for LLM agent consumption."""
    return SKILL_MD
