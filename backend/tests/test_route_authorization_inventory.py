"""Regression guard: every API route must declare its authorization.

GET routes need an authz dependency (visibility or permission).  Write
routes (POST/PUT/PATCH/DELETE) need the decision point in ``core/authz.py``
or a guard built on it; see the second half of this module.

Walks the FastAPI app's route table and fails the build if a GET route
under ``/api/`` lacks one of the recognised authz dependencies (or is
not on the explicit public/whitelisted set).

This catches the common regression of adding a new GET endpoint and
forgetting ``require_permission`` / ``get_org_context``.

When a new endpoint is genuinely public or self-scoped (no leak risk),
add it to ``_AUTHZ_WHITELIST`` with a short justification.

Endpoints that are *known* to lack authz but are not yet fixed live in
``_KNOWN_DEBT``.  They are exempt from the test — but a second test
fails if a known-debt entry is no longer present (so we can't silently
re-introduce a regression on a fixed route either).
"""

import ast
import inspect
import textwrap

from fastapi.routing import APIRoute

# Routes that are intentionally accessible without an authz dependency.
# Each entry must include a comment documenting why.
_AUTHZ_WHITELIST: dict[str, str] = {
    # Public auth/health endpoints
    "/api/auth/status": "public — used by frontend to detect login state",
    "/api/auth/me": "self-scoped to current user",
    "/api/auth/csrf": "public — bootstrap CSRF token",
    "/api/auth/login": "public — start OIDC flow",
    "/api/auth/callback": "public — OIDC callback",
    "/api/auth/logout": "public — terminate session",
    "/api/health": "public health check",
    "/api/health/ready": "public health check",
    # Self-scoped endpoints (effective_person_id ensures caller-only data)
    "/api/tasks/my": "self-scoped via effective_person_id",
    "/api/tasks/inbox": "self-scoped via effective_person_id",
    "/api/activity/inbox": "self-scoped via effective_person_id in handler",
    "/api/roles/my-permissions": "self-scoped (caller's own roles + perms)",
    "/api/org-placements/my-requests": "self-scoped via current_user.id filter",
    "/api/chat/{conversation_id}": "self-scoped via current_user.id in handler",
    "/api/chat/attachments/{attachment_id}/preview": "owner-check in handler",
    # Mattermost webhook endpoints (authenticated via shared secret)
    "/api/mattermost/slash": "authenticated via shared secret in body",
    "/api/mattermost/verify-link": "public — link verification",
    # WebAuthn registration/authentication ceremony
    "/api/webauthn/authenticate/options": "public — start authn ceremony",
    "/api/webauthn/authenticate/verify": "public — complete authn ceremony",
    # Tenant-wide reference data (intentionally readable by any logged-in user
    # because the authn middleware already gates /api/*)
    "/api/tags": "ministerie-breed gedeeld per ontwerp",
    "/api/tags/search": "ministerie-breed gedeeld per ontwerp",
    "/api/tags/tree": "ministerie-breed gedeeld per ontwerp",
    "/api/tags/{tag_id}": "ministerie-breed gedeeld per ontwerp",
    "/api/edge-types": "schema-data, ministerie-breed",
    "/api/edge-types/{id}": "schema-data, ministerie-breed",
    "/api/edge-types/valid": "schema-data, ministerie-breed",
    "/api/edge-schema-rules": "schema-data, ministerie-breed",
    "/api/skill.md": "skill markdown bundle, no PII",
    "/api/roles": "globale rol-definitielijst, ministerie-breed referentiedata",
    # Org-chart is bewust ministerie-breed leesbaar binnen de tenant.
    # Mutaties hebben wel require_permission("org:manage") + check_org_scope.
    "/api/organisatie": "org-chart is ministerie-breed by design",
    "/api/organisatie/search": "org-chart, ministerie-breed",
    "/api/organisatie/tree-children": "org-chart, ministerie-breed (lazy-load van children)",  # noqa: E501
    "/api/organisatie/managed-by/{person_id}": "org-chart, ministerie-breed",
    "/api/organisatie/{id}": "org-chart, ministerie-breed",
    "/api/organisatie/{id}/history/managers": "org-chart history, ministerie-breed",
    "/api/organisatie/{id}/history/namen": "org-chart history, ministerie-breed",
    "/api/organisatie/{id}/history/parents": "org-chart history, ministerie-breed",
    "/api/organisatie/{id}/personen": (
        "team-member lijst, ministerie-breed (publiek profiel: naam, "
        "functie, default email — geen private nummers)"
    ),
    # Externe organisaties zijn als KvK-nummers publieke NL-data, geen
    # gevoelige interne contactdata.
    "/api/externe-organisaties": "externe org-referentie, publieke NL-data",
    "/api/externe-organisaties/{id}": "externe org-referentie, publieke NL-data",
    # LLM corpus-gaps geeft ministerie-brede dossier-overview voor
    # planningsdoeleinden; geen gevoelige PII.
    "/api/llm/corpus-gaps": "ministerie-brede planningsdata, geen PII",
    # Graph endpoints bouwen op CorpusNode dat al via apply_org_filter
    # gescopeerd is (zie nodes/list_nodes en repository).
    "/api/graph/search": "bouwt op CorpusNode (al gefilterd via PR #263)",
    "/api/graph/path": "bouwt op CorpusNode (al gefilterd via PR #263)",
    # Notifications: handlers filter on effective_person_id explicitly
    # in the route body (zie notifications.py — list/count/dashboard-stats
    # roepen effective_person_id aan; detail/replies gaan door
    # _check_notification_owner). De inventory test detecteert die
    # in-body call niet, dus expliciet whitelisten.
    "/api/notifications": "self-scoped via effective_person_id in handler",
    "/api/notifications/count": "self-scoped via effective_person_id in handler",
    "/api/notifications/dashboard-stats": "self-scoped via effective_person_id",
    "/api/notifications/{id}": "self-scoped via _check_notification_owner",
    "/api/notifications/{id}/replies": "self-scoped via _check_notification_owner",
}

# Whole-prefix whitelists (every GET under this prefix is exempt).
_AUTHZ_PREFIX_WHITELIST: tuple[str, ...] = (
    "/api/auth/",
    "/api/health",
    "/api/webauthn/",
    "/api/mattermost/",
    # Public initiatief-pagina: opt-in per initiatief via public_page_enabled,
    # endpoint returnt 404 als flag uit staat. Bewust bypassed om anonymous
    # access naar /c/:slug mogelijk te maken.
    "/api/public/",
)

# Known-debt: GET routes that still lack authz but are scheduled for a
# follow-up PR.  Once empty, this guard is fully active.
_KNOWN_DEBT: set[str] = set()

# Recognised dependency-callable names that satisfy the authz requirement.
_AUTHZ_DEP_NAMES = {
    "_check",  # require_permission inner closure
    "get_org_context",
    "get_permission_context",
    "get_initiatief_context",
    "get_admin_user",  # AdminUser annotation
    "effective_person_id",
    "_authz_requires",  # core.authz.requires
}


def _route_has_authz_dep(route: APIRoute) -> bool:
    """True if any of the route's dependencies match _AUTHZ_DEP_NAMES."""

    def _walk(deps):
        for dep in deps:
            call = getattr(dep, "call", None)
            if call is not None and call.__name__ in _AUTHZ_DEP_NAMES:
                return True
            if _walk(getattr(dep, "dependencies", [])):
                return True
        return False

    return _walk(route.dependant.dependencies)


def _collect_get_routes(app) -> list[APIRoute]:
    return [
        r
        for r in app.routes
        if isinstance(r, APIRoute) and "GET" in r.methods and r.path.startswith("/api/")
    ]


def _is_exempt(path: str) -> bool:
    if path in _AUTHZ_WHITELIST or path in _KNOWN_DEBT:
        return True
    return any(path.startswith(p) for p in _AUTHZ_PREFIX_WHITELIST)


def test_all_get_routes_have_authz_dep(_test_app):
    """Fail if any GET /api/* route is missing an authz dependency.

    Whitelisted entries (intentionally public/self-scoped) and known-debt
    entries (scheduled for follow-up) are exempt.
    """
    offenders: list[str] = []

    for route in _collect_get_routes(_test_app):
        if _is_exempt(route.path):
            continue
        if _route_has_authz_dep(route):
            continue
        offenders.append(route.path)

    assert not offenders, (
        "New GET routes without authz dependency. Either add one of "
        f"{sorted(_AUTHZ_DEP_NAMES)}, whitelist in _AUTHZ_WHITELIST with "
        "justification, or — if this is genuine debt — add to _KNOWN_DEBT:\n"
        + "\n".join(f"  - {p}" for p in sorted(offenders))
    )


def test_known_debt_is_still_unauthorized(_test_app):
    """Fail if a route in _KNOWN_DEBT has acquired an authz dependency.

    Forces removal from the debt list when fixed, so the test stays a
    meaningful regression guard rather than a stale wishlist.
    """
    fixed: list[str] = []
    actual_paths = {r.path for r in _collect_get_routes(_test_app)}

    for route in _collect_get_routes(_test_app):
        if route.path not in _KNOWN_DEBT:
            continue
        if _route_has_authz_dep(route):
            fixed.append(route.path)

    # Routes in the debt list that no longer exist also need to be cleaned up.
    stale = sorted(_KNOWN_DEBT - actual_paths)

    assert not fixed, (
        "These routes are now protected — remove them from _KNOWN_DEBT:\n"
        + "\n".join(f"  - {p}" for p in sorted(fixed))
    )
    assert not stale, (
        "These routes no longer exist — remove them from _KNOWN_DEBT:\n"
        + "\n".join(f"  - {p}" for p in stale)
    )


# ---------------------------------------------------------------------------
# Write routes: every POST/PUT/PATCH/DELETE asks core.authz (or a guard on it)
# ---------------------------------------------------------------------------

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Dependencies that decide a write: the authz factory, system-only
# permissions and the admin users.
_WRITE_AUTHZ_DEPS = {
    "requires.<locals>._authz_requires",
    "require_system_permission.<locals>._check",
    "get_admin_user",
    "get_super_admin_user",
}

# Calls that decide a write when made in the route body or in one of its
# dependencies (other helpers are not followed): ``authz.require`` and the
# guards of ``core.authority`` (``require_can_*``, and the eenheid guard that
# delegates to ``authz.require``).
_WRITE_AUTHZ_CALLS = {"require", "require_permission_on_eenheid"}
_WRITE_AUTHZ_CALL_PREFIX = "require_can_"

# Write routes that need no resource decision.  One line of reason each.
_WRITE_ALLOWLIST: dict[str, str] = {
    "POST /api/auth/onboarding": "self-scoped: own onboarding state",
    "POST /api/auth/onboarding/dismiss": "self-scoped: own onboarding state",
    "POST /api/auth/onboarding/refresh": "self-scoped: own onboarding state",
    "POST /api/auth/request-access": "access request by the caller themselves",
    "POST /api/org-placements/request": "own placement request; a manager decides",
    "POST /api/chat": "own conversation; write tools ask authz in chat_service",
    "POST /api/chat/confirm": "own conversation; tools ask authz in chat_service",
    "POST /api/chat/upload": "own chat attachment",
    "POST /api/llm/gap-analysis": "no mutation: advice on text in the request",
    "POST /api/llm/kompas-guidance": "no mutation: advice on text in the request",
    "POST /api/llm/suggest-tags": "no mutation: advice on text in the request",
    "POST /api/leads/parse-intake": (
        "no mutation: LLM parse of text in the request; creating the lead is "
        "decided on POST /api/leads"
    ),
    "POST /api/mattermost/link-code": "self-scoped: link own Mattermost account",
    "DELETE /api/mattermost/link": "self-scoped: unlink own Mattermost account",
    "POST /api/mattermost/slash": "authenticated via shared secret",
    "POST /api/mattermost/verify-link": "public link verification, rate limited",
    "POST /api/notifications/send": "direct message; sender must be the caller",
    "POST /api/notifications/{id}/react": "self-scoped: thread participant",
    "POST /api/notifications/{id}/reply": "self-scoped: own notification",
    "PUT /api/notifications/{id}/read": "self-scoped: own notification",
    "PUT /api/notifications/read-all": "self-scoped: own notifications",
    "POST /api/webauthn/authenticate/options": "public authn ceremony",
    "POST /api/webauthn/authenticate/verify": "public authn ceremony",
    "POST /api/webauthn/register/options": "self-scoped: own credential",
    "POST /api/webauthn/register/verify": "self-scoped: own credential",
    "DELETE /api/webauthn/credentials/{credential_id}": "self-scoped: own credential",
}

# Write routes not yet on core.authz, grouped by file with the check they use
# today.  Migrating a route means removing it here (the second test below
# insists).  Never add to this list.
_WRITE_KNOWN_DEBT: set[str] = {
    # bijlage.py: require_permission + check_resource_org_scope
    "POST /api/nodes/{node_id}/bijlage",
    "DELETE /api/nodes/{node_id}/bijlage",
    # fcc.py: require_permission (fcc:sync)
    "POST /api/fcc/conflicts/{opdracht_id}/resolve",
    "POST /api/fcc/opdrachten/{opdracht_id}/push",
    "POST /api/fcc/sync/trigger",
    # import_export.py: require_permission (import_export:import)
    "POST /api/import/edges",
    "POST /api/import/nodes",
    "POST /api/import/politieke-inputs",
    # initiatief.py: _require_access / _resolve_access_level; create unchecked
    "POST /api/initiatieven",
    "PUT /api/initiatieven/{id}",
    "PUT /api/initiatieven/{id}/settings",
    "DELETE /api/initiatieven/{id}",
    # initiatief_update.py: _require_access
    "POST /api/initiatieven/{initiatief_id}/updates",
    "PUT /api/initiatieven/{initiatief_id}/updates/{post_id}",
    "DELETE /api/initiatieven/{initiatief_id}/updates/{post_id}",
    "POST /api/initiatieven/{initiatief_id}/updates/{post_id}/publish",
    "POST /api/initiatieven/{initiatief_id}/updates/{post_id}/unpublish",
    # lead_columns.py: _require_access
    "POST /api/initiatieven/{initiatief_id}/columns",
    "POST /api/initiatieven/{initiatief_id}/columns/reorder",
    "PUT /api/initiatieven/{initiatief_id}/columns/{column_id}",
    "DELETE /api/initiatieven/{initiatief_id}/columns/{column_id}",
    # mattermost_channels.py: _can_manage_link / _resolve_initiatief / _resolve_lead
    "POST /api/initiatieven/{initiatief_id}/mattermost-channels",
    "POST /api/leads/{lead_id}/mattermost-channels",
    "PATCH /api/mattermost-channels/{link_id}",
    "DELETE /api/mattermost-channels/{link_id}",
    # opdrachten.py: require_permission + check_resource_org_scope
    "POST /api/opdrachten",
    "PUT /api/opdrachten/{id}",
    "DELETE /api/opdrachten/{id}",
    "POST /api/opdrachten/{id}/match-contacts",
    "POST /api/opdrachten/match-contacts-bulk",
    "POST /api/opdrachten/{opdracht_id}/koppelingen",
    "DELETE /api/opdrachten/{opdracht_id}/koppelingen/{koppeling_id}",
    # organisatie.py: require_permission + _check_eenheid_write_access
    "PUT /api/organisatie/{id}",
    # parlementair.py: require_permission (parlementair:review / :import)
    "PATCH /api/parlementair/edges/{edge_id}",
    "PUT /api/parlementair/edges/{edge_id}/approve",
    "PUT /api/parlementair/edges/{edge_id}/reject",
    "PUT /api/parlementair/edges/{edge_id}/reset",
    "POST /api/parlementair/imports/reprocess",
    "POST /api/parlementair/imports/trigger",
    "PUT /api/parlementair/imports/{import_id}/reject",
    "PUT /api/parlementair/imports/{import_id}/reopen",
    # parlementair_abonnement.py: _require_initiatief_toegang (visibility)
    "POST /api/initiatieven/{initiatief_id}/abonnementen",
    "POST /api/initiatieven/{initiatief_id}/abonnementen/suggesties",
    "PATCH /api/initiatieven/{initiatief_id}/abonnementen/{abonnement_id}",
    "DELETE /api/initiatieven/{initiatief_id}/abonnementen/{abonnement_id}",
    "PUT /api/initiatieven/{initiatief_id}/signaalcontext",
    # people.py: require_permission (people:create)
    "POST /api/people",
    # samenwerkingsverband.py: require_permission
    "POST /api/samenwerkingsverbanden",
    "PUT /api/samenwerkingsverbanden/{id}",
    "DELETE /api/samenwerkingsverbanden/{id}",
    "POST /api/samenwerkingsverbanden/{id}/leden",
    "PUT /api/samenwerkingsverbanden/{id}/leden/{lid_id}",
    "DELETE /api/samenwerkingsverbanden/{id}/leden/{lid_id}",
    # stakeholder_assessments.py: _check_scope_access
    "POST /api/stakeholder-assessments",
    "PUT /api/stakeholder-assessments/{id}",
    "DELETE /api/stakeholder-assessments/{id}",
    # sharing.py: _require_share_authority (org:manage per eenheid, on authz)
    "POST /api/sharing",
    "DELETE /api/sharing/{share_id}",
    # tags.py: require_permission (tenant-wide vocabulary, see core.authz)
    "POST /api/tags",
    "PUT /api/tags/{tag_id}",
    "DELETE /api/tags/{tag_id}",
}


def _called_names(fn) -> set[str]:
    """Names of every function called in *fn*'s source (``f()`` and ``x.f()``)."""
    try:
        source = textwrap.dedent(inspect.getsource(fn))
    except (OSError, TypeError):
        return set()
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def _decides(names: set[str]) -> bool:
    # A local wrapper such as ``_require_can_place`` counts as its guard.
    return bool(names & _WRITE_AUTHZ_CALLS) or any(
        n.lstrip("_").startswith(_WRITE_AUTHZ_CALL_PREFIX) for n in names
    )


def _write_route_is_authorized(route: APIRoute) -> bool:
    """True if the route depends on or calls a write decision."""
    callables = [route.endpoint]

    def _walk(deps) -> bool:
        for dep in deps:
            call = getattr(dep, "call", None)
            if call is not None:
                if getattr(call, "__qualname__", "") in _WRITE_AUTHZ_DEPS:
                    return True
                callables.append(call)
            if _walk(getattr(dep, "dependencies", [])):
                return True
        return False

    if _walk(route.dependant.dependencies):
        return True
    return any(_decides(_called_names(fn)) for fn in callables)


def _write_routes(app) -> dict[str, APIRoute]:
    return {
        f"{method} {route.path}": route
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/")
        for method in route.methods & _WRITE_METHODS
    }


def test_all_write_routes_ask_authz(_test_app):
    """Fail if a write route decides nothing through core.authz.

    Fix a failure with ``Depends(requires(...))`` or an ``authz.require(...)``
    call, never by adding to ``_WRITE_KNOWN_DEBT``.  Truly self-scoped routes
    go in ``_WRITE_ALLOWLIST`` with a reason.
    """
    offenders = sorted(
        key
        for key, route in _write_routes(_test_app).items()
        if key not in _WRITE_ALLOWLIST
        and key not in _WRITE_KNOWN_DEBT
        and not _write_route_is_authorized(route)
    )
    assert not offenders, (
        "Write routes without an authz decision; use core.authz "
        "(requires/require) or a core.authority guard:\n"
        + "\n".join(f"  - {k}" for k in offenders)
    )


def test_write_known_debt_is_still_debt(_test_app):
    """Fail when a debt route has been migrated or no longer exists."""
    routes = _write_routes(_test_app)
    fixed = sorted(
        key
        for key in _WRITE_KNOWN_DEBT
        if key in routes and _write_route_is_authorized(routes[key])
    )
    stale = sorted((_WRITE_KNOWN_DEBT | set(_WRITE_ALLOWLIST)) - set(routes))
    assert not fixed, "Migrated; remove from _WRITE_KNOWN_DEBT:\n" + "\n".join(
        f"  - {k}" for k in fixed
    )
    assert not stale, "No longer exist; remove from the lists:\n" + "\n".join(
        f"  - {k}" for k in stale
    )
