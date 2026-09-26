"""Regression guard: every API route must declare its authorization.

Walks the FastAPI app's route table.  A GET route under ``/api/`` must make
a read decision: ``requires(...)``, a permission guard, the caller's
visibility (``get_org_context`` / ``get_initiatief_context``, or an
``apply_*_filter``), or a ``require``/``can`` call on ``core.authz``.
Merely taking the ``PermissionContext`` decides nothing.  A write route
(POST/PUT/PATCH/DELETE) must ask ``core/authz.py`` or a ``core.authority``
guard.  Calls are found in the route and its dependencies, and one level
into the helpers they call (a local ``_require_can_*`` wrapper counts only
because it calls a real decision).

A route that is genuinely public or self-scoped goes on an allowlist with
a short reason; an allowlist entry for a route that no longer exists fails.
"""

import ast
import inspect
import textwrap

from fastapi.routing import APIRoute

from bouwmeester.core import authority

# Routes that are intentionally accessible without an authz dependency.
# Each entry must include a comment documenting why.
_AUTHZ_WHITELIST: dict[str, str] = {
    # Public auth/health endpoints
    "/api/auth/status": "public — used by frontend to detect login state",
    "/api/auth/me": "self-scoped to current user",
    "/api/auth/login": "public — start OIDC flow",
    "/api/auth/callback": "public — OIDC callback",
    "/api/auth/logout": "public — terminate session",
    "/api/health/ready": "public health check",
    # Self-scoped endpoints (effective_person_id ensures caller-only data)
    "/api/tasks/my": "self-scoped via effective_person_id",
    "/api/tasks/inbox": "self-scoped via effective_person_id",
    "/api/activity/inbox": "self-scoped via effective_person_id in handler",
    "/api/roles/my-permissions": "self-scoped (caller's own roles + perms)",
    "/api/org-placements/my-requests": "self-scoped via current_user.id filter",
    "/api/chat/{conversation_id}": "self-scoped via current_user.id in handler",
    "/api/chat/attachments/{attachment_id}/preview": "owner-check in handler",
    "/api/mattermost-channels/search": (
        "self-scoped: a private channel only for the caller's own Mattermost "
        "account when it is a member"
    ),
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
    # Mutations go through core.authz (org:manage on the eenheid) and core.authority.
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

# Dependencies that decide something by themselves, by qualified name.
_DECIDING_DEPS = {
    "requires.<locals>._authz_requires",  # core.authz.requires
    "require_permission.<locals>._check",
    "require_system_permission.<locals>._check",
    "get_admin_user",  # AdminUser annotation
    "get_super_admin_user",
}

# A permission held anywhere gates a module, it decides no write.
_READ_ONLY_GATES = {"require_permission.<locals>._check"}

# Dependencies that decide a read: the caller's visibility, or data scoped to
# the caller themselves.
_READ_DEPS = {"get_org_context", "get_initiatief_context", "effective_person_id"}

# Calls that decide: ``core.authz``, the list filters built on visibility, and
# the eenheden whose placements the caller decides (``core.authority``).
_READ_CALLS = {"require", "can", "managed_subtree_ids"}
_READ_CALL_PREFIX = "apply_"
_WRITE_CALLS = {"require"}


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


def _is_guard(name: str) -> bool:
    """A ``require_can_*`` guard that really exists in ``core.authority``."""
    return name.startswith("require_can_") and callable(getattr(authority, name, None))


def _is_read_decision(name: str) -> bool:
    return (
        name in _READ_CALLS
        or (name.startswith(_READ_CALL_PREFIX) and name.endswith("_filter"))
        or _is_guard(name)
    )


def _is_write_decision(name: str) -> bool:
    return name in _WRITE_CALLS or _is_guard(name)


def _decides(fn, is_decision) -> bool:
    """*fn* calls a decision, directly or through one local helper."""
    names = _called_names(fn)
    if any(is_decision(n) for n in names):
        return True
    scope = getattr(fn, "__globals__", {})
    for name in names:
        helper = scope.get(name)
        if inspect.isfunction(helper) and helper.__module__.startswith("bouwmeester"):
            if any(is_decision(n) for n in _called_names(helper)):
                return True
    return False


def _route_decides(route: APIRoute, dep_names: set[str], is_decision) -> bool:
    """True if a dependency in *dep_names* or a called decision guards *route*."""
    callables = [route.endpoint]

    def _walk(deps) -> bool:
        for dep in deps:
            call = getattr(dep, "call", None)
            if call is not None:
                if getattr(call, "__qualname__", "") in dep_names:
                    return True
                callables.append(call)
            if _walk(getattr(dep, "dependencies", [])):
                return True
        return False

    if _walk(route.dependant.dependencies):
        return True
    return any(_decides(fn, is_decision) for fn in callables)


def _route_has_read_decision(route: APIRoute) -> bool:
    return _route_decides(route, _DECIDING_DEPS | _READ_DEPS, _is_read_decision)


def _collect_get_routes(app) -> list[APIRoute]:
    return [
        r
        for r in app.routes
        if isinstance(r, APIRoute) and "GET" in r.methods and r.path.startswith("/api/")
    ]


def _is_exempt(path: str) -> bool:
    if path in _AUTHZ_WHITELIST:
        return True
    return any(path.startswith(p) for p in _AUTHZ_PREFIX_WHITELIST)


def test_all_get_routes_have_authz_dep(_test_app):
    """Fail if any GET /api/* route makes no read decision."""
    offenders = sorted(
        route.path
        for route in _collect_get_routes(_test_app)
        if not _is_exempt(route.path) and not _route_has_read_decision(route)
    )
    assert not offenders, (
        "GET routes without a read decision. Use requires(...), a permission "
        "guard, the caller's visibility (get_org_context / "
        "get_initiatief_context) or authz.require/can, or whitelist in "
        "_AUTHZ_WHITELIST with a reason:\n" + "\n".join(f"  - {p}" for p in offenders)
    )


# ---------------------------------------------------------------------------
# Write routes: every POST/PUT/PATCH/DELETE asks core.authz (or a guard on it)
# ---------------------------------------------------------------------------

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Write routes that need no resource decision.  One line of reason each.
_WRITE_ALLOWLIST: dict[str, str] = {
    "POST /api/authz/evaluations": "read-only: the caller's own rights via can()",
    "POST /api/auth/onboarding": "self-scoped: own onboarding state",
    "POST /api/auth/onboarding/dismiss": "self-scoped: own onboarding state",
    "POST /api/auth/onboarding/refresh": "self-scoped: own onboarding state",
    "POST /api/auth/request-access": "access request by the caller themselves",
    "POST /api/org-placements/request": "own placement request; a manager decides",
    "POST /api/chat": "own conversation; write tools ask authz in chat_service",
    "POST /api/chat/confirm": "own conversation; tools ask authz in chat_service",
    "POST /api/chat/upload": "own chat attachment",
    "POST /api/llm/gap-analysis": "no mutation: reads a dossier the caller can see",
    "POST /api/llm/kompas-guidance": "no mutation: reads a dossier the caller can see",
    "POST /api/llm/suggest-tags": "no mutation: advice on text in the request",
    "POST /api/leads/parse-intake": (
        "no mutation: LLM parse of text in the request; creating the lead is "
        "decided on POST /api/leads"
    ),
    "POST /api/initiatieven": (
        "personal initiatief: the creator becomes its eigenaar, the payload "
        "grants nothing else (test_authz_initiatief pins that)"
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


def _write_route_is_authorized(route: APIRoute) -> bool:
    return _route_decides(route, _DECIDING_DEPS - _READ_ONLY_GATES, _is_write_decision)


def _write_routes(app) -> dict[str, APIRoute]:
    return {
        f"{method} {route.path}": route
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/")
        for method in route.methods & _WRITE_METHODS
    }


def test_all_write_routes_ask_authz(_test_app):
    """Fail if a write route decides nothing through core.authz.

    Fix a failure with ``Depends(requires(...))``, an ``authz.require(...)``
    call or a ``core.authority`` guard.  Truly self-scoped routes go in
    ``_WRITE_ALLOWLIST`` with a reason.
    """
    offenders = sorted(
        key
        for key, route in _write_routes(_test_app).items()
        if key not in _WRITE_ALLOWLIST and not _write_route_is_authorized(route)
    )
    assert not offenders, (
        "Write routes without an authz decision; use core.authz "
        "(requires/require) or a core.authority guard:\n"
        + "\n".join(f"  - {k}" for k in offenders)
    )


def test_allowlists_name_existing_routes(_test_app):
    """Fail when an allowlisted route no longer exists."""
    stale_writes = sorted(set(_WRITE_ALLOWLIST) - set(_write_routes(_test_app)))
    get_paths = {r.path for r in _collect_get_routes(_test_app)}
    stale_gets = sorted(set(_AUTHZ_WHITELIST) - get_paths)
    stale = stale_writes + stale_gets
    assert not stale, "No longer exist; remove from the allowlists:\n" + "\n".join(
        f"  - {k}" for k in stale
    )
