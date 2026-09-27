"""Tenant-wide operations need a system role; one resource is decided where it lives.

Uses ``world`` from ``tests/authz_world.py``.  A role on an eenheid never
does for a sync, an import or schema management, not even on the top
eenheid and not even when the role carries the permission.  Pushing one
opdracht to FCC or analysing one dossier is decided on that resource.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from bouwmeester.models.opdracht import OpdrachtNode
from bouwmeester.models.person import Person
from bouwmeester.models.role import Role, RolePermission
from tests.authz_world import World, add, opdracht, request
from tests.factories import client_as, grant_role, make_person, place

_TENANT_WIDE_PERMS = (
    "fcc:sync",
    "import_export:import",
    "import_export:export",
    "parlementair:import",
    "org:manage",
    "config:manage",
)


async def _scoped_ops(w: World, eenheid: str) -> Person:
    """Someone holding every tenant-wide permission, on one eenheid only."""
    role = Role(
        id=f"ops_{uuid.uuid4().hex[:8]}", naam="Eenheidsbeheer", level="unit", rank=5
    )
    await add(w, role)
    w.db.add_all(
        RolePermission(role_id=role.id, permission_id=p) for p in _TENANT_WIDE_PERMS
    )
    person = await make_person(w.db, f"Beheer {eenheid}")
    await place(w.db, person, w.org[eenheid])
    await grant_role(w.db, person, role.id, w.org[eenheid])
    return person


@pytest.fixture
def stub_sync(monkeypatch):
    """The full org sync stops at its first step instead of calling out."""

    async def _stop(_db):
        raise HTTPException(status_code=418, detail="sync reached")

    monkeypatch.setattr("bouwmeester.api.routes.admin_sync.sync_tooi", _stop)


# (method, path, request that stops harmlessly once the guard lets it through,
# status then, may platform_admin?).  A refusal is a 403 before validation.
_BAD_UUID = {"params": {"actor_id": "geen-uuid"}}
_ONBEKEND = {"params": {"item_type": "onbekend"}}
TENANT_WIDE_ROUTES = [
    ("POST", "/api/fcc/sync/trigger", {}, 200, False),  # FCC not configured
    ("GET", "/api/fcc/conflicts", {}, 200, False),
    ("POST", "/api/import/nodes", {}, 422, True),  # no file
    ("POST", "/api/import/edges", {}, 422, True),
    ("POST", "/api/import/politieke-inputs", {}, 422, True),
    ("GET", "/api/export/corpus", {}, 200, True),
    ("POST", "/api/parlementair/imports/trigger", _BAD_UUID, 422, False),
    ("POST", "/api/parlementair/imports/reprocess", _ONBEKEND, 422, False),
    ("POST", "/api/admin/sync/all", {}, 418, False),  # sync_tooi stubbed
    ("POST", "/api/admin/reconciliation/manual-merge", {"json": {}}, 422, False),
    ("POST", "/api/edge-types", {"json": {}}, 422, True),
    ("DELETE", "/api/edge-types/bestaat-niet", {}, 404, True),
    ("POST", "/api/edge-schema-rules", {"json": {}}, 422, True),
    ("DELETE", "/api/edge-schema-rules/geen-uuid", {}, 422, True),
]  # fmt: skip


@pytest.mark.parametrize(
    ("method", "path", "probe", "allowed", "platform_admin_may"),
    TENANT_WIDE_ROUTES,
    ids=[f"{r[0]} {r[1]}" for r in TENANT_WIDE_ROUTES],
)
async def test_tenant_wide_needs_system_role(
    world, stub_sync, method, path, probe, allowed, platform_admin_may
):
    callers = {
        "top_eenheid": await _scoped_ops(world, "ministerie"),
        "manager": world.person["manager"],
        "super_admin": world.person["super_admin"],
        "platform_admin": world.person["platform_admin"],
    }
    got = {}
    for who, person in callers.items():
        async with client_as(world.db, person) as c:
            got[who] = (await c.request(method, path, **probe)).status_code
    assert got == {
        "top_eenheid": 403,
        "manager": 403,
        "super_admin": allowed,
        "platform_admin": allowed if platform_admin_may else 403,
    }


# Settings trusted with credentials or data (secrets, addresses, and the
# switches deciding where data goes) are super_admin's.
CONFIG_KEYS = [
    ("MATTERMOST_WEBHOOK_TOKEN", False),  # would let one act as any user
    ("MATTERMOST_BOT_TOKEN", False),
    ("MATTERMOST_URL", False),  # the bot token is sent there
    ("ANTHROPIC_API_KEY", False),
    ("VLAM_API_URL", False),  # prompts with corpus data go there
    ("FCC_ODATA_URL", False),
    ("LLM_PROVIDER", False),  # which provider receives corpus content
    ("MATTERMOST_ENABLED", False),
    ("FCC_SYNC_ENABLED", False),
    ("FCC_PUSH_ENABLED", False),  # writes our data into FCC
    ("FCC_USE_MOCK", False),
    ("FCC_PROJECT_ENTITY", False),
    ("LLM_MODEL", True),
]  # fmt: skip


@pytest.mark.parametrize(("key", "platform_admin_may"), CONFIG_KEYS)
async def test_security_config_is_super_admin_only(
    world, monkeypatch, key, platform_admin_may
):
    import bouwmeester.api.routes.admin as admin_routes

    monkeypatch.setattr(admin_routes, "_defaults_seeded", False)
    got, offered = {}, {}
    for who in ("platform_admin", "super_admin"):
        async with client_as(world.db, world.person[who]) as c:
            listing = await c.get("/api/admin/config")
            resp = await c.patch(f"/api/admin/config/{key}", json={"value": "x"})
        got[who] = resp.status_code
        offered[who] = next(e for e in listing.json() if e["key"] == key)["editable"]
    assert got == {
        "platform_admin": 200 if platform_admin_may else 403,
        "super_admin": 200,
    }
    # The listing offers editing exactly where the PATCH route allows it.
    assert offered == {who: status == 200 for who, status in got.items()}


@pytest.mark.parametrize(
    ("who", "expected"), [("platform_admin", 403), ("super_admin", 200)]
)
async def test_database_dump_is_super_admin_only(world, who, expected):
    service = "bouwmeester.services.database_backup_service"
    with (
        patch(f"{service}.export_database", return_value=(b"x", "backup.tar.gz")),
        patch(f"{service}._get_alembic_revision", return_value="head"),
    ):
        dump = await request(world, who, "GET", "/api/admin/database/export")
        info = await request(world, who, "GET", "/api/admin/database/info")
    assert (dump.status_code, info.status_code) == (expected, expected)


@pytest.mark.parametrize(
    ("who", "expected"), [("role_only", 403), ("viewer", 403), ("team_editor", 200)]
)
async def test_suggest_tags_needs_a_node_writer(world, who, expected):
    """Tag suggestions spend LLM budget."""
    with patch(
        "bouwmeester.api.routes.llm.get_llm_service_for",
        new=AsyncMock(return_value=None),
    ):
        resp = await request(
            world, who, "POST", "/api/llm/suggest-tags", {"title": "x"}
        )
    assert resp.status_code == expected, resp.text


@pytest.mark.parametrize("route", ["gap-analysis", "kompas-guidance"])
@pytest.mark.parametrize(
    ("dossier", "expected"),
    [("{node_team}", 200), ("{node_elders}", 404), ("missing", 404), ("bad", 422)],
)
async def test_llm_analysis_needs_a_visible_dossier(world, route, dossier, expected):
    dossier_id = {"missing": str(uuid.uuid4()), "bad": "geen-uuid"}.get(
        dossier, dossier
    )
    body = {"dossier_id": dossier_id, "step_node_types": ["doel"]}
    resp = await request(world, "team_editor", "POST", f"/api/llm/{route}", body)
    assert resp.status_code == expected, resp.text


async def test_fcc_push_is_decided_on_the_opdracht(world):
    """Push is disabled in tests, so 400 means the decision let it through."""
    opd = await add(world, opdracht(world, "Opdracht", "team"))
    callers = {
        "above": await _scoped_ops(world, "afdeling"),
        "beside": await _scoped_ops(world, "elders"),
        "manager": world.person["manager"],
        "super_admin": world.person["super_admin"],
    }
    results = {}
    for who, person in callers.items():
        async with client_as(world.db, person) as c:
            results[who] = (
                await c.post(f"/api/fcc/opdrachten/{opd.id}/push")
            ).status_code
    missing = await request(
        world, "super_admin", "POST", f"/api/fcc/opdrachten/{uuid.uuid4()}/push"
    )
    # beside cannot see the opdracht, so a refusal does not reveal it (404)
    assert results == {"above": 400, "beside": 404, "manager": 403, "super_admin": 400}
    assert missing.status_code == 404


async def test_fcc_conflict_resolution_names_only_readable_nodes(world):
    """fcc:sync on the afdeling; the instrument and a koppeling lie elsewhere."""
    opd = await add(
        world,
        opdracht(
            world,
            "Conflictopdracht",
            "team",
            instrument_id=world.res["node_elders"],
            sync_status="conflict",
        ),
    )
    await add(
        world,
        OpdrachtNode(opdracht_id=opd.id, node_id=world.res["node_elders"]),
        OpdrachtNode(opdracht_id=opd.id, node_id=world.res["node_team"]),
    )
    ops = await _scoped_ops(world, "afdeling")
    with patch(
        "bouwmeester.services.fcc_import_service.FccImportService.pull_single",
        new=AsyncMock(),
    ):
        async with client_as(world.db, ops) as c:
            resp = await c.post(
                f"/api/fcc/conflicts/{opd.id}/resolve",
                json={"resolution": "use_theirs"},
            )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["instrument_id"] == str(world.res["node_elders"])  # on the record
    assert body["instrument"] is None
    koppelingen = [k["node_id"] for k in body["node_koppelingen"]]
    assert koppelingen == [str(world.res["node_team"])]
    assert "Dossier elders" not in resp.text
