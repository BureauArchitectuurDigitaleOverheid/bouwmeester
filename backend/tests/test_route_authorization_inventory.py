"""Regression guard: every API GET route must declare an authz dependency.

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
