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
| `zad logs` | Follow Zad deployment logs (production) |
| `just db-shell` | Open psql shell |
| `just worker-logs` | Follow worker service logs |
| `just import-parlementair` | Manually trigger parlementair import via API |
| `just decrypt-seed` | Decrypt seed person data (.age → .json) |
| `just encrypt-seed` | Encrypt seed person data (.json → .age) |

## Architecture

- **Backend**: FastAPI + SQLAlchemy 2.0 async + Alembic + PostgreSQL (asyncpg)
- **Frontend**: React + TypeScript + React Query + @nldd/design-system + Vite
- **Infra**: Docker Compose (dev)
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
- **Dropdowns**: `CreatableSelect` when the user may add an option inline, otherwise `Select` (`nldd-dropdown` around a native `<select>`, with `size` and `width`)
- **Rich text**: ALL description/beschrijving fields MUST use `RichTextFormField` (edit) and `RichTextDisplay` (view) — never use plain `<textarea>` for descriptions
- **Layout**: `Header.tsx` renders page title from `pageTitles` map — pages should NOT have their own `<h1>`
- **Sidebar**: Nav items defined in `components/layout/Sidebar.tsx`
- **Route definitions**: `App.tsx`

### Design system (`@nldd/design-system`)

- **Elements**: use `nldd-*` elements directly; every one the app renders is imported in `components/nldd/register.ts` (`register.test.ts` fails otherwise). After a package upgrade run `node scripts/generate-nldd-types.mjs` to regenerate `nldd-elements.d.ts`.
- **Events**: never `onClick`/`onChange` on an `nldd-*` element; bridge with `useNlddEvent` from `components/nldd/events.ts`, or use a wrapper below.
- **Buttons**: `NlddButton` (label in `text`, not children; `compactBelowSm` shows only the icon on phones) and `NlddIconButton`. A raw `<button>` only for operable text, with `className="plain-button"`.
- **Clickable list rows**: `NlddListItemButton` (action) or `NlddListItemLink` (route), both in `components/nldd/NlddLink.tsx`.
- **Icons**: `Icon` takes nldd icon names only; `scripts/validate-nldd-markup.mjs` rejects unknown names.
- **Colors**: `Badge color=` and the color maps use `EntityColor`, Rijkshuisstijl names (`lintblauw`, `mosgroen`, ...), never hex values or hand-picked palette steps.
- **Labels**: no uppercase or letter-spaced labels. A section label is `nldd-title size={6}`, a small caption `nldd-text size="xs" weight="medium" color="secondary"`.
- **Loading**: `LoadingSpinner` for a page or panel; a raw `nldd-activity-indicator` only inline in a button or row.
- **CSS**: layout goes through `nldd-container` attributes. `utilities.css` holds the few classes nothing in the design system covers; `scripts/validate-css-classes.mjs` checks every class used has a rule.
- **Checks**: `npx tsc -b && npx eslint src && node scripts/validate-nldd-markup.mjs && node scripts/validate-nldd-tokens.mjs && node scripts/validate-css-classes.mjs && npx vitest run` (in `frontend/`).

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
- Color maps (`NODE_TYPE_COLORS`, `ORGANISATIE_TYPE_BADGE_COLORS`, `TASK_PRIORITY_COLORS`, ...) in `types/index.ts`, all `EntityColor`

## Key data relationships

```
Person
├── Task (assignee_id)
├── ResourcePermission (eigenaar/betrokken/adviseur on any resource)
├── PersonRole (role assignments, system or scoped to eenheid)
├── OrganisatieEenheid (member via organisatie_eenheid_id)
├── OrganisatieEenheid (manager via manager_id)
├── Activity (actor_id)
├── Notification (person_id)
└── Absence (person_id / substitute_id)

CorpusNode (dossier/doel/instrument/beleidskader/maatregel/politieke_input/probleem/effect/beleidsoptie)
├── Edge (from_node_id / to_node_id, typed via EdgeType)
├── Task (node_id)
├── ResourcePermission (resource_type=corpus_node, resource_id=node_id)
└── NodeTag (node_id → Tag, hierarchical tagging)

Tag (hierarchical, parent_id self-ref)
└── NodeTag (many-to-many with CorpusNode)

ParlementairItem (tracks imported parliamentary items: moties, kamervragen, toezeggingen, etc.)
├── SuggestedEdge (proposed edges to corpus nodes, pending review)
├── CorpusNode (corpus_node_id, the created politieke_input node)
└── type discriminator (motie, kamervraag, toezegging, amendement, ...)

Initiatief
├── Lead (initiatief_id) — funnel-stage tracking
├── ResourcePermission (eigenaar/contributor/viewer per persoon of eenheid)
├── InitiatiefUpdatePost (publication posts; published_at IS NULL = concept)
└── slug (unique URL-segment, eenmalig instelbaar via /settings)

StakeholderAssessment (belang/houding/invloed per persoon op een scope)
├── scope_type=corpus_node OR initiatief
├── scope_id (polymorphic FK; access-check in route, geen DB-FK)
└── unique (person_id, scope_type, scope_id)
```

## Initiatief settings & publieke pagina

Per-initiatief feature-toggles (eigenaar-only via `PUT /api/initiatieven/{id}/settings`):

- `funnel_enabled` — toont engagement_type + drie 1-5 scores op leads van dit initiatief
- `public_page_enabled` — opt-in publieke pagina op `/c/:slug`
- `score_strategisch_label` / `score_politiek_label` / `score_positie_label` — eigen labels die de defaults overschrijven

Slug-rules in `backend/bouwmeester/core/slug.py`: lowercase, `[a-z0-9-]`, niet leeg, niet in `RESERVED_SLUGS`. Eenmalig instelbaar via UI (immutable na save in v1).

Publieke endpoint `GET /api/public/initiatieven/by-slug/{slug}`:
- Zit in `_PUBLIC_PREFIXES` van `auth_required.py` — geen auth nodig
- Returnt 404 als slug niet bestaat OF `public_page_enabled=false` (geen 403 om bestaan niet te lekken)
- Two-step query (lookup zonder relations, daarna eager-load) om timing-side-channel te beperken
- Toont alleen naam/beschrijving/kleur + gepubliceerde `InitiatiefUpdatePost` records (`published_at IS NOT NULL`)
- Frontend route `/c/:slug` in `App.tsx` zit buiten `AuthGate`; `<meta name="robots" content="noindex">` op de pagina, plus blanket `Disallow: /` in `frontend/public/robots.txt`

## Seed data and PII

Person data in the seed script is **not** stored in git as plaintext. Instead:

- `backend/scripts/seed_persons.json` — plaintext person data, **gitignored**
- `backend/scripts/seed_persons.json.age` — age-encrypted version, **committed**
- The seed script (`backend/scripts/seed.py`) loads from the JSON file. If missing, it generates placeholder persons with a warning.

### Working with seed person data

```bash
just decrypt-seed    # Decrypt .age → .json (needs ~/.age/key.txt)
just encrypt-seed    # Encrypt .json → .age (uses public keys from justfile)
```

To edit person data: decrypt, edit the JSON, re-encrypt, commit the `.age` file.

### New developer setup

1. `brew install age`
2. `age-keygen -o ~/.age/key.txt` — send the public key to a team member
3. Team member adds your public key to `encrypt-seed` in `justfile` and re-encrypts
4. `just decrypt-seed` to get the person data
5. `just reset-db` works without decryption too (uses placeholder persons)

## Access whitelist

Production access is restricted to whitelisted email addresses stored in the `whitelist_email` database table, managed via the admin UI (Beheer > Toegangslijst).

- Backend module: `bouwmeester/core/whitelist.py` — cache refreshed at startup and on whitelist changes, enforced in `AuthRequiredMiddleware` (all API routes) and `auth_status()` (friendly frontend response)
- When the whitelist table is empty, all emails are allowed (backwards compatible for local dev)
- Non-whitelisted users can request access via the AccessDeniedPage; admins approve/deny from Beheer > Verzoeken

## Authorization patterns

`AuthRequiredMiddleware` enforces authentication on `/api/*`. **Authorization** (which records a user may see/mutate) is decided in one place, `core/authz.py`:

- **List endpoints** filter with the caller's visibility: `org_ctx: OrgContext = Depends(get_org_context)` and `apply_org_filter(stmt, Model.organisatie_eenheid_id, org_ctx)` in the repo. The column names the rule: on a `CorpusNode` (or alias) it is `apply_node_filter`, on a `Task` `apply_task_filter`; `apply_opdracht_filter` for opdrachten, `apply_initiatief_filter` / `apply_lead_filter` with `get_initiatief_context`. Each filter has its row form next to it in `core/org_context.py` (`sees_node`, `sees_task`, `sees_opdracht`), which `core.authz` uses for `*:read`.
- **Detail endpoints** ask a read: `_authz=Depends(requires("<domain>:read", "<type>"))` (`path_param=` when the id is not `{id}`), or `await require(db, perm_ctx, "node:read", "corpus_node", id)` for an id from a body. A refused read is a 404, like a missing one. Reads answer from the same visibility as the lists, so a list and a detail never disagree (`tests/test_authz_consistency.py` checks every person against every resource).
- **Mutations**: `_authz=Depends(requires("node:update", "corpus_node"))`, or `await require(...)` in the body; `can(...)` returns a bool. A refused write on something the caller cannot read is a 404 too (no existence oracle); 403 only when they can see it. Creating: pass where it will live, `eenheid_id=` or `place=` (the new record or a dict with its placing fields: a task's `node_id`/`organisatie_eenheid_id`, a lead's `initiatief_id`/`organisatie_eenheid_id`, an opdracht's two eenheden (both need `opdracht:create`), an edge's two nodes, an eenheid's `parent_id`/`type`), or ask the parent with the child's permission (`require(db, ctx, "edge:create", "corpus_node", from_id)`). Moving an existing lead, task or opdracht: `authz.require_move(db, ctx, type, record, data.model_dump(exclude_unset=True))`. Sub-records under a parent in the path ask on the parent (`requires("lead_update:create", "lead", path_param="lead_id")`) and load the record with `api.deps.get_child_or_404`. Every id a body links to (a node, an opdracht, a parent task) is checked too (`services/task_rules.py` for tasks). Chat write tools call the same functions. `require_permission` + visibility checks on a write are not used: the first counts a permission held anywhere, the second is visibility.
- **System permissions**: `require_system_permission` (backend) and `hasSystemPermission` (frontend) only for tenant-wide actions (syncs, merges, imports, exports, platform settings). Everything about a record or an eenheid goes through `core.authz` (backend) and `useCan` / `GET /api/authz/eenheden` (frontend). Corpus and edge export (`import_export:export`) is a deliberate system-role exception to read visibility, like `database:backup`.
- **Tenant-wide-by-design** endpoints (`tags`, `organisatie`-chart, `edge-types`, `roles`) are intentionally readable by every authenticated user. Whitelist them in `backend/tests/test_route_authorization_inventory.py`.

`can()` resolves in this order, first match wins: (0) `<type>:read` on a node, task, edge, opdracht, initiatief, lead or sub-record is visibility (`org_context` / `initiatief_context`, the rule lists use): a node, task or opdracht is visible when one of its eenheden is visible (an opdracht has two), when it has none, when the caller holds a resource role on it that grants reading, for a node also when it is shared with one of the caller's eenheden, for a task when it is assigned to the caller, and a task without eenheid through its node; an edge when both nodes are; a lead through its initiatief, a lead role, or (without initiatief) its eenheid, only a lead with neither is tenant-wide; tasks and opdrachten also need their module permission (`task:read`, `opdracht:read`) somewhere, for writing as well (without it only a resource role on the opdracht itself counts, and the assignee still reads their own task); (1) super_admin or the permission from a system role; synced eenheden (`bron` other than `handmatig`) are read-only except for super_admin; (2) a resource role on the resource itself (`RESOURCE_ROLE_PERMISSIONS`); an eenheid's eigenaar role is a role on an eenheid and applies below it too; (3) its parent, per the `_DELEGATIONS` table (edge -> either node, lead -> initiatief, task without eenheid -> node, sub-records -> their initiatief/lead/scope, a suggested edge -> `parlementair:review` on its item's node); (4) the permission held on the resource's eenheid or one above it, or through an *edit* share; (5) a tenant-wide fallback only for `corpus_node`, `lead`, `opdracht`, `parlementair_item`, `samenwerkingsverband`, `tag` and creating a `person`, and only without an eenheid; creating an `organisatie_eenheid` below a parent needs `org:create` on that parent (a role there or above it, or the eigenaar role of an external organisation there or above it), internal and external alike; a new external root (a stakeholder at the top) is free for whoever holds `org:create`, a new internal root is system-only. Moving an eenheid (`authority.require_can_move_eenheid`) needs that authority on the parent it leaves and the one it goes to (a manager of both when an internal eenheid is involved), and taking an external eenheid out of the organisation (`org_tree.touches_organisation` changes) needs a manager of the parent it leaves. Only the creator of a new external root becomes its eigenaar. A new lead without initiatief and eenheid lands in the caller's own eenheid (`services/lead_rules.py`, `authz.own_eenheid_where`); only system roles create one that lives nowhere. Deleting an eenheid is decided like dissolving it (`api.deps.require_can_end_eenheid`). Corpus rule: reading follows org visibility; only *writing* is tenant-wide for a node without eenheid (anyone holding the permission through any role), a node with an eenheid is written by rights on that eenheid. Seeing an eenheid never implies writing there, but writing always implies seeing: `org_context` makes the subtree of every eenheid where a scoped role grants a write permission visible, and a resource role or an edit share that lets you write a node, task or opdracht also lets you read it. The module docstring of `core/authz.py` has both tables. Code that holds only a person uses `authz.perm_ctx_for(db, person_id)` and `authz.visibility(db, perm_ctx)` (org and initiatief context, built once per request).

The frontend asks rights through `POST /api/authz/evaluations` (AuthZEN-shaped batch, subject is always the caller) via `useCan` (`frontend/src/hooks/useCan.ts`) instead of deriving them from roles. Besides `can()` actions it answers:

- `properties.anywhere: true` without an id: is there any eenheid where the caller may create this (generic "Nieuwe taak", a lead without initiatief). For `lead:create` on `lead` this is exactly what `POST /api/leads` without initiatief and eenheid accepts; a lead in an initiatief is `lead:create` on that `initiatief`.
- Grant actions, decided by calling the `core/authority.py` guard the route calls (a refusal is `false`): `resource_role:grant` (resource `{type, id}`, `properties.rol`, optional `properties.target_person_id` or `properties.target_eenheid_id`), `resource_role:revoke` (resource `{type, id}`, exactly one of `properties.target_person_id` / `properties.target_eenheid_id`, optional `properties.rol`), `role:assign` (resource type `role`, `properties.role_id`, optional `eenheid_id` and `target_person_id`; or `properties.anywhere: true` without `role_id`: any role to someone else, in `eenheid_id` or anywhere), `role:revoke` (resource type `role` with the assignment id), `eenheid:set_manager` and `eenheid:dissolve` (resource `organisatie_eenheid` with id), `person:place` (resource `person`, optional id, `properties.eenheid_id`, optional `properties.ending` and `properties.contact`), `parlementair:name_owner` (resource `{type: "corpus_node", id}`, `properties.target_person_id`: make that person the eigenaar when completing a review, `require_can_name_owner`), `eenheid:share` (resource `{type: "organisatie_eenheid", id}` = the source, `properties.target_eenheid_id`: `require_can_share`, the guard `POST /api/sharing` calls). Without a target the question is "to someone other than me"; `person:place` without an id asks about another account (or a contact with `contact`).
- Creating an eenheid: `org:create` on `organisatie_eenheid` with `properties.eenheid_type` and optional `properties.eenheid_id` = the parent (without a type: an internal eenheid below `eenheid_id`).
- `GET /api/authz/eenheden?action=<org:manage|org:update|org:create|people:assign_role|person:place>` (with `org:create` optionally `&eenheid_type=`) returns `{"all": bool, "ids": [...]}`: the eenheden where the caller may do that (`all: true` for system roles, `ids` then empty). Same answers as asking the evaluation endpoint per eenheid; use it for pickers and admin lists instead of one question per eenheid.

The inventory test (`backend/tests/test_route_authorization_inventory.py`) fails CI on any GET `/api/*` route that makes no read decision (`requires(...)`, a permission guard, `get_org_context` / `get_initiatief_context`, an `apply_*_filter`, or an `authz.require`/`can` call; taking the `PermissionContext` alone is not a decision), and on any POST/PUT/PATCH/DELETE route that does not ask `core.authz` (or a `core.authority` guard, `require_system_permission`, `AdminUser`). A local `_require_can_*` wrapper counts only because it calls one of those. Public or self-scoped routes sit on an allowlist with a reason; there is no debt list.

### Authority over grants (`core/authority.py`)

Anything that changes *who has access to what* goes through a `require_can_*` guard in `core/authority.py`, never through `require_permission` or a visibility check: placements, naming a manager, moving or dissolving an eenheid, assigning or revoking roles, deciding placement requests, editing a person (emails are identity), granting resource roles. REST routes and chat tools call the same guards.

- A role on an eenheid applies to everything below it (`rights_on_eenheid`). Seeing an eenheid never implies authority over it.
- Nobody grants themselves a role; nobody decides their own placement request. The role assignments of an eenheid are listed for who assigns roles there (`require_can_assign_roles_in`).
- Only **trusted** placements give access: visibility (own eenheden; members of an internal eenheid also read up its line, members of an external eenheid, even one hanging inside the organisation, see that eenheid only), the implicit viewer role, edit shares, and roles held by an eenheid (resource roles granted to an eenheid reach only its trusted members). Trusted means `PersonOrganisatieEenheid.bron` in `TRUSTED_PLACEMENT_BRONNEN` (`models/person_organisatie.py`): `leidinggevende` (made or approved by whoever decides about its members, `can_confirm_members`: a manager of the eenheid or above it, and for an external organisation outside the internal one also whoever holds `org:manage` on it, typically its creator-eigenaar) or an official sync (`tk_odata`, `kabinet_yaml`, `abd_scrape`, `roo_leidinggevende`). `handmatig` (contact administration by anyone with `people:update`) and `detachering` (a manager linking own staff to an external organisation) are informational only; the UI shows them as before. Moving an eenheid never confirms its placements. A manager (or that eigenaar) confirms a contact placement by placing the person there again or by approving a placement request; either way a pending request for it is settled as approved (`authority.approve_placement_requests`). Changing or reopening a trusted placement (`authority.bron_after_change`) keeps it trusted only for who may confirm the members; anyone else turns a manager's placement into contact administration and is refused on a sync's placement. Onboarding (`needs_placement`) also looks at trusted placements only. Placements of accounts (logged in, agent, or holding a role) from before deploy were confirmed by migration `7c1e5a9d3b20`; contact placements were not.
- Membership is resolved in one place: `repositories/org_tree.py` `membership_ids_select` / `get_membership_ids` (with the SQL predicates `placement_active`, `placement_trusted`). Never join `PersonOrganisatieEenheid` yourself to decide access or to route work (a parliamentary review task goes to the eenheid of its owners' memberships).
- `DELETE /api/organisatie/{id}` refuses (409) while anything still refers to the eenheid (`org_tree.eenheid_references`): sub-eenheden, placements, nodes, leads, tasks, opdrachten, grants, shares. Otherwise those items would lose their eenheid and become tenant-wide.
- Naming the eigenaar of a node while completing a parliamentary review goes through `require_can_name_owner`: a first eigenaar must be able to read the node, and you name yourself only when you already edit it.
- Security-relevant app settings (secrets and `*_URL` addresses in `PATCH /api/admin/config/{key}`) are super_admin only; platform_admin changes the rest.
- Tenant-wide actions (syncs, merges) use `require_system_permission`, not `require_permission`.
- Tree walks for access (`repositories/org_tree.py`) read `OrganisatieEenheid.parent_id`; internal org types live in `INTERNAL_EENHEID_TYPES`.
- Tests: `tests/test_grant_authority.py`, built on `tests/factories.py`.

### Testing rights locally

Local dev has no identity provider. Without a pick in the header's person picker every request is allowed; after picking someone, the backend (dev mode only, via the `bm_dev_person` cookie) runs every request with that person's real roles and memberships. `just seed` gives managers, `ministry_admin`s, editors and viewers across a real tree to pick from.

## Pull requests

- Always branch from the latest remote main: `git fetch origin && git checkout -b <branch> origin/main`
- Do **not** merge PRs automatically, even when CI is green. After CI passes, critically review your own diff (correctness, edge cases, missing tests, style) and present your findings to the user. The user may request changes — expect one or more review rounds.
- Only merge when the user explicitly says so (e.g. "merge it", "looks good, merge").
- Use squash merge with `--delete-branch` by default.

## Database

- PostgreSQL 16, connection via Docker Compose on `localhost:5432`
- Credentials: `bouwmeester` / `bouwmeester` / `bouwmeester` (user/password/db)
- Migrations run locally via `uv` (not inside Docker), connecting to localhost
- DB may not always be running — use `just up` or `docker compose up -d db` first
