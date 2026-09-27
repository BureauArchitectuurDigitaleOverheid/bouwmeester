"""Tenant-wide operations and chat write tools on the decision point.

Uses ``world`` from ``tests/authz_world.py``.  The questions:

- A tenant-wide operation (syncs, imports, schema management) needs a system
  role.  A role on an eenheid does not do, not even on the top one and not
  even when that role carries the permission.
- An operation on one resource (reviewing a parliamentary item, pushing one
  opdracht to FCC) is decided where that resource lives.
- A chat write tool, slash command or suggestion button refuses what its
  REST route refuses.
- An LLM analysis of a dossier needs to see that dossier.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from bouwmeester.core.authz import can
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.mattermost_channel_link import MattermostChannelLink
from bouwmeester.models.mattermost_user import MattermostUser
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.parlementair_item import SuggestedEdge
from bouwmeester.models.person import Person
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.role import Role, RolePermission
from bouwmeester.models.suggested_lead import SuggestedLead
from bouwmeester.models.tag import Tag
from bouwmeester.repositories.mattermost_channel_link import (
    MattermostChannelLinkRepository,
)
from bouwmeester.services.chat_service import _authorize_write_tool
from bouwmeester.services.mattermost_slash_service import (
    _NO_WRITE,
    MattermostSlashService,
)
from tests.authz_world import World, add_directie_admin, make_item, perm_ctx
from tests.factories import client_as, grant_role, make_person, place

# Every permission that guards a tenant-wide operation.
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
    w.db.add(role)
    await w.db.flush()
    w.db.add_all(
        RolePermission(role_id=role.id, permission_id=p) for p in _TENANT_WIDE_PERMS
    )
    person = await make_person(w.db, f"Beheer {eenheid}")
    await place(w.db, person, w.org[eenheid])
    await grant_role(w.db, person, role.id, w.org[eenheid])
    return person


# ---------------------------------------------------------------------------
# Tenant-wide operations: a system role, nothing else
# ---------------------------------------------------------------------------

# (method, path, request that stops harmlessly once the guard lets it through,
# status then, may platform_admin?).  platform_admin only holds import_export:*
# and config:manage; super_admin holds everything.  A refusal is a 403 before
# the request is even validated.
_BAD_UUID = {"params": {"actor_id": "geen-uuid"}}
TENANT_WIDE_ROUTES = [
    ("POST", "/api/fcc/sync/trigger", {}, 200, False),  # FCC not configured
    ("GET", "/api/fcc/conflicts", {}, 200, False),
    ("POST", "/api/import/nodes", {}, 422, True),  # no file
    ("POST", "/api/import/edges", {}, 422, True),
    ("POST", "/api/import/politieke-inputs", {}, 422, True),
    ("GET", "/api/export/corpus", {}, 200, True),
    ("POST", "/api/parlementair/imports/trigger", _BAD_UUID, 422, False),
    (
        "POST",
        "/api/parlementair/imports/reprocess",
        {"params": {"item_type": "onbekend"}},
        422,
        False,
    ),
    ("POST", "/api/admin/sync/all", {}, 418, False),  # sync_tooi stubbed
    ("POST", "/api/admin/reconciliation/manual-merge", {"json": {}}, 422, False),
    ("POST", "/api/edge-types", {"json": {}}, 422, True),
    ("DELETE", "/api/edge-types/bestaat-niet", {}, 404, True),
    ("POST", "/api/edge-schema-rules", {"json": {}}, 422, True),
    ("DELETE", "/api/edge-schema-rules/geen-uuid", {}, 422, True),
]


@pytest.fixture
def stub_sync(monkeypatch):
    """The full org sync stops at its first step instead of calling out."""

    async def _stop(_db):
        raise HTTPException(status_code=418, detail="sync reached")

    monkeypatch.setattr("bouwmeester.api.routes.admin_sync.sync_tooi", _stop)


@pytest.mark.parametrize(
    ("method", "path", "probe", "allowed", "platform_admin_may"),
    TENANT_WIDE_ROUTES,
    ids=[f"{r[0]} {r[1]}" for r in TENANT_WIDE_ROUTES],
)
async def test_tenant_wide_needs_system_role(
    world, stub_sync, method, path, probe, allowed, platform_admin_may
):
    callers = {
        # every tenant-wide permission, but on the top eenheid only
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


# Settings the app trusts with credentials or data (secrets, addresses, and
# the switches that decide where data goes or which external system is
# called) are super_admin's; ordinary settings are platform_admin's too.
CONFIG_KEYS = [
    ("MATTERMOST_WEBHOOK_TOKEN", False),  # would let one act as any user
    ("MATTERMOST_BOT_TOKEN", False),
    ("MATTERMOST_URL", False),  # the bot token is sent there
    ("ANTHROPIC_API_KEY", False),
    ("VLAM_API_URL", False),  # prompts with corpus data go there
    ("FCC_ODATA_URL", False),
    ("LLM_PROVIDER", False),  # which provider receives corpus content
    ("MATTERMOST_ENABLED", False),  # starts sending to Mattermost
    ("FCC_SYNC_ENABLED", False),
    ("FCC_PUSH_ENABLED", False),  # writes our data into FCC
    ("FCC_USE_MOCK", False),
    ("FCC_PROJECT_ENTITY", False),
    ("LLM_MODEL", True),
]


@pytest.mark.parametrize(("key", "platform_admin_may"), CONFIG_KEYS)
async def test_security_config_is_super_admin_only(
    world, monkeypatch, key, platform_admin_may
):
    import bouwmeester.api.routes.admin as admin_routes

    monkeypatch.setattr(admin_routes, "_defaults_seeded", False)
    got = {}
    for who in ("platform_admin", "super_admin"):
        async with client_as(world.db, world.person[who]) as c:
            await c.get("/api/admin/config")
            resp = await c.patch(f"/api/admin/config/{key}", json={"value": "x"})
        got[who] = resp.status_code
    assert got == {
        "platform_admin": 200 if platform_admin_may else 403,
        "super_admin": 200,
    }


# ---------------------------------------------------------------------------
# One resource: decided where it lives
# ---------------------------------------------------------------------------


# (who, node of the item, expected status of PUT .../reject)
REVIEW_CASES = [
    ("team_editor", "node_team", 200),
    ("afd_editor", "node_team", 200),  # a role applies to everything below
    ("team_editor", "node_directie", 403),  # visible above, not writable
    ("manager", "node_elders", 404),  # not visible: as if it did not exist
    ("team_editor", "node_free", 200),  # a node without eenheid is tenant-wide
    ("viewer", "node_free", 403),  # viewers do not review
    ("team_editor", None, 200),  # no node yet: like a new node without eenheid
]


@pytest.mark.parametrize(
    ("who", "node", "expected"),
    REVIEW_CASES,
    ids=[f"{c[0]}-{c[1]}" for c in REVIEW_CASES],
)
async def test_parlementair_review_is_decided_on_its_node(world, who, node, expected):
    item = await make_item(world, node)
    async with client_as(world.db, world.person[who]) as c:
        resp = await c.put(f"/api/parlementair/imports/{item.id}/reject")
    assert resp.status_code == expected, resp.text


# (who, item node, target node, expected status of approve)
APPROVE_CASES = [
    # the reviewer of the item's node; the target may lie out of their reach
    ("team_editor", "node_team", "node_elders", 200),
    # an item on a node without eenheid is reviewed by any reviewer
    ("team_editor", "node_free", "node_team", 200),
    # a reviewer who holds no edge:create still approves: it is their mandate
    ("ministry_admin", "node_directie", "node_team", 200),
]


@pytest.mark.parametrize(
    ("who", "node", "target", "expected"),
    APPROVE_CASES,
    ids=[f"{c[0]}-{c[1]}-{c[2]}" for c in APPROVE_CASES],
)
async def test_approving_a_suggested_edge_is_the_reviewers_mandate(
    world, who, node, target, expected
):
    await add_directie_admin(world, "ministry_admin", "Ministeriebeheerder")
    item = await make_item(world, node)
    suggested = SuggestedEdge(
        parlementair_item_id=item.id,
        target_node_id=world.res[target],
        edge_type_id=world.res["edge_type"],
        confidence=0.9,
    )
    world.db.add(suggested)
    await world.db.flush()
    async with client_as(world.db, world.person[who]) as c:
        approve = await c.put(f"/api/parlementair/edges/{suggested.id}/approve")
        # rejecting creates nothing: reviewing the item is enough
        reject = await c.put(f"/api/parlementair/edges/{suggested.id}/reject")
    assert approve.status_code == expected, approve.text
    assert reject.status_code == 200, reject.text


async def test_fcc_push_is_decided_on_the_opdracht(world):
    """Pushing one opdracht needs fcc:sync where the opdracht lives.

    Push is disabled in tests, so 400 means the decision let it through.
    """
    opdracht = Opdracht(
        type="opdracht",
        titel="Opdracht",
        begrotingsjaar=2026,
        opdrachtgever_id=world.org["team"].id,
    )
    world.db.add(opdracht)
    await world.db.flush()
    above = await _scoped_ops(world, "afdeling")
    beside = await _scoped_ops(world, "elders")
    url = f"/api/fcc/opdrachten/{opdracht.id}/push"
    results = {}
    for who, person in (
        ("above", above),
        ("beside", beside),
        ("manager", world.person["manager"]),
        ("super_admin", world.person["super_admin"]),
    ):
        async with client_as(world.db, person) as c:
            results[who] = (await c.post(url)).status_code
    async with client_as(world.db, world.person["super_admin"]) as c:
        missing = await c.post(f"/api/fcc/opdrachten/{uuid.uuid4()}/push")
    # beside cannot see the opdracht, so a refusal does not reveal it (404)
    assert results == {"above": 400, "beside": 404, "manager": 403, "super_admin": 400}
    assert missing.status_code == 404


# ---------------------------------------------------------------------------
# Chat write tools refuse what their REST routes refuse
# ---------------------------------------------------------------------------


async def _tag(w: World) -> str:
    name = f"tag-{uuid.uuid4().hex[:6]}"
    w.db.add(Tag(name=name))
    await w.db.flush()
    return name


# (tool, chat args, REST method, REST path, REST body); ``{key}`` is a
# resource of ``world``, ``{tag}`` a fresh tag name.
PARITY = [
    ("update_node", {"node_id": "{node_directie}", "title": "x"},
     "PUT", "/api/nodes/{node_directie}", {"title": "x"}),
    ("update_node", {"node_id": "{node_team}", "title": "x"},
     "PUT", "/api/nodes/{node_team}", {"title": "x"}),
    ("update_task", {"task_id": "{task_team}", "title": "x"},
     "PUT", "/api/tasks/{task_team}", {"title": "x"}),
    ("create_task", {"node_id": "{node_directie}", "title": "x"},
     "POST", "/api/tasks", {"node_id": "{node_directie}", "title": "x"}),
    ("create_task", {"node_id": "{node_team}", "title": "x"},
     "POST", "/api/tasks", {"node_id": "{node_team}", "title": "x"}),
    ("add_tag_to_node", {"node_id": "{node_directie}", "tag_name": "{tag}"},
     "POST", "/api/nodes/{node_directie}/tags", {"tag_name": "{tag}"}),
    ("add_tag_to_node", {"node_id": "{node_afdeling}", "tag_name": "{tag}"},
     "POST", "/api/nodes/{node_afdeling}/tags", {"tag_name": "{tag}"}),
]  # fmt: skip


def _fill_placeholders(value, values: dict[str, str]):
    """Fill ``{key}`` in a string, or in every value of a dict."""
    if isinstance(value, dict):
        return {k: _fill_placeholders(v, values) for k, v in value.items()}
    return value.format(**values)


@pytest.mark.parametrize("who", ["team_editor", "afd_editor", "viewer"])
@pytest.mark.parametrize(
    ("tool", "args", "method", "path", "body"),
    PARITY,
    ids=[f"{p[0]}-{next(iter(p[1].values()))[1:-1]}" for p in PARITY],
)
async def test_chat_tool_refuses_what_rest_refuses(
    world, who, tool, args, method, path, body
):
    values = {k: str(v) for k, v in world.res.items()} | {"tag": await _tag(world)}
    person = world.person[who]
    refusal = await _authorize_write_tool(
        tool, _fill_placeholders(args, values), world.db, person.id
    )
    async with client_as(world.db, person) as c:
        resp = await c.request(
            method,
            _fill_placeholders(path, values),
            json=_fill_placeholders(body, values),
        )
    assert resp.status_code in (200, 201, 403), resp.text
    assert (refusal is None) is (resp.status_code != 403), (refusal, resp.text)


# (who, tool, args, allowed).  The lead routes are migrated separately; these
# tools ask what those routes ask: lead:update on the lead, lead:create in
# the user's own eenheid.
LEAD_CASES = [
    ("afd_editor", "update_lead", {"lead_id": "{lead}"}, True),
    ("role_only", "update_lead", {"lead_id": "{lead}"}, True),  # contributor
    ("team_editor", "update_lead", {"lead_id": "{lead}"}, False),  # below owner
    ("viewer", "move_lead", {"lead_id": "{lead}", "stage": "koelkast"}, False),
    ("afd_editor", "move_lead", {"lead_id": "{lead}", "stage": "koelkast"}, True),
    ("team_editor", "add_lead_activity", {"lead_id": "{lead}", "content": "x"}, False),
    ("afd_editor", "add_lead_activity", {"lead_id": "{lead}", "content": "x"}, True),
    ("team_editor", "update_lead", {"lead_id": "{lead_free}"}, True),  # unscoped
    ("viewer", "update_lead", {"lead_id": "{lead_free}"}, False),
    ("team_editor", "create_lead", {"title": "x"}, True),
    ("manager", "create_lead", {"title": "x"}, True),
    ("viewer", "create_lead", {"title": "x"}, False),
    ("role_only", "create_lead", {"title": "x"}, False),  # placed nowhere
]


@pytest.mark.parametrize(
    ("who", "tool", "args", "allowed"),
    LEAD_CASES,
    ids=[f"{c[0]}-{c[1]}-{next(iter(c[2].values()))}" for c in LEAD_CASES],
)
async def test_chat_lead_tools_ask_authz(world, who, tool, args, allowed):
    values = {k: str(v) for k, v in world.res.items()}
    refusal = await _authorize_write_tool(
        tool, _fill_placeholders(args, values), world.db, world.person[who].id
    )
    assert (refusal is None) is allowed, refusal


async def test_chat_lead_tools_match_the_decision_point(world):
    """update_lead refuses exactly when authz refuses lead:update."""
    for who in world.person:
        ctx = await perm_ctx(world, who)
        for lead in ("lead", "lead_free"):
            refusal = await _authorize_write_tool(
                "update_lead",
                {"lead_id": str(world.res[lead])},
                world.db,
                world.person[who].id,
            )
            expected = await can(world.db, ctx, "lead:update", "lead", world.res[lead])
            assert (refusal is None) is expected, (who, lead)


# ---------------------------------------------------------------------------
# LLM analyses read a dossier: only one the caller can see
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route", ["gap-analysis", "kompas-guidance"])
@pytest.mark.parametrize(
    ("dossier", "expected"),
    [("node_team", 200), ("node_elders", 404), ("missing", 404), ("bad", 422)],
)
async def test_llm_analysis_needs_a_visible_dossier(world, route, dossier, expected):
    dossier_id = {"missing": str(uuid.uuid4()), "bad": "geen-uuid"}.get(
        dossier, str(world.res.get(dossier))
    )
    async with client_as(world.db, world.person["team_editor"]) as c:
        resp = await c.post(
            f"/api/llm/{route}",
            json={"dossier_id": dossier_id, "step_node_types": ["doel"]},
        )
    assert resp.status_code == expected, resp.text


# ---------------------------------------------------------------------------
# Mattermost slash commands and suggestion buttons ask what REST asks
# ---------------------------------------------------------------------------


def _mm_id() -> str:
    return uuid.uuid4().hex[:26]


@pytest.fixture
async def slash(world, monkeypatch):
    """A linked channel of the initiatief, plus someone who only sees it.

    Channel membership is not what these tests are about: every channel
    counts as one the caller may link (see test_leaks_graph_chat.py).
    """
    from bouwmeester.services import mattermost_slash_service

    monkeypatch.setattr(
        mattermost_slash_service, "channel_link_refusal", AsyncMock(return_value=None)
    )
    init_viewer = await make_person(world.db, "Initiatiefkijker")
    world.db.add(
        ResourcePermission(
            person_id=init_viewer.id,
            resource_type="initiatief",
            resource_id=world.res["initiatief"],
            rol="viewer",
        )
    )
    world.person["init_viewer"] = init_viewer
    channel = _mm_id()
    world.db.add(
        MattermostChannelLink(
            channel_id=channel,
            channel_name="kanaal",
            channel_display_name="kanaal",
            scope_type="initiatief",
            scope_id=world.res["initiatief"],
        )
    )
    mm_users = {}
    for who, person in world.person.items():
        mm_users[who] = _mm_id()
        world.db.add(
            MattermostUser(
                person_id=person.id,
                mattermost_user_id=mm_users[who],
                mattermost_username=who,
            )
        )
    await world.db.flush()
    return {"channel": channel, "mm": mm_users}


# (who, command, on the linked channel?, allowed)
SLASH_CASES = [
    ("init_viewer", "koppel initiatief {naam}", False, False),
    ("role_only", "koppel initiatief {naam}", False, True),  # contributor
    ("init_viewer", "ontkoppel", True, False),
    ("role_only", "ontkoppel", True, True),
    ("init_viewer", "volg Digitale Dienst", True, False),
    ("afd_editor", "volg Digitale Dienst", True, True),
]


@pytest.mark.parametrize(
    ("who", "command", "linked", "allowed"),
    SLASH_CASES,
    ids=[f"{c[0]}-{c[1].split()[0]}" for c in SLASH_CASES],
)
async def test_slash_command_writes_ask_authz(
    world, slash, who, command, linked, allowed
):
    naam = (await world.db.get(Initiatief, world.res["initiatief"])).naam
    channel = slash["channel"] if linked else _mm_id()
    result = await MattermostSlashService(world.db).handle_command(
        slash["mm"][who],
        command.format(naam=naam),
        channel_id=channel,
        channel_name="kanaal",
    )
    assert (_NO_WRITE not in result["text"]) is allowed, result["text"]
    if command.startswith("koppel"):
        link = await MattermostChannelLinkRepository(world.db).get_by_channel_id(
            channel
        )
        assert (link is not None) is allowed


@pytest.mark.parametrize(
    ("who", "allowed"), [("init_viewer", False), ("afd_editor", True)]
)
async def test_suggestion_buttons_ask_authz(world, slash, who, allowed):
    suggested = SuggestedLead(
        source_post_id=_mm_id(),
        source_channel_id=slash["channel"],
        initiatief_id=world.res["initiatief"],
        proposed_title="Gemeente",
        raw_text="Gemeente vraagt om een gesprek.",
        status="pending",
    )
    world.db.add(suggested)
    await world.db.flush()
    service = MattermostSlashService(world.db)
    context = {"suggested_lead_id": str(suggested.id)}
    with patch.object(MattermostSlashService, "_update_thread_post", AsyncMock()):
        result = await service.handle_action(
            slash["mm"][who], "create_lead_from_suggestion", context
        )
    assert (result["ephemeral_text"] != _NO_WRITE) is allowed, result
    assert (suggested.status == "approved_new") is allowed


@pytest.mark.parametrize(
    ("who", "action", "allowed"),
    [
        ("init_viewer", "reject_suggestion", False),
        ("role_only", "reject_suggestion", True),  # contributor: initiatief:update
        ("init_viewer", "link_lead_to_suggestion", False),
        ("role_only", "link_lead_to_suggestion", True),
    ],
)
async def test_suggested_lead_review_is_initiatief_update(
    world, slash, who, action, allowed
):
    suggested = SuggestedLead(
        source_post_id=_mm_id(),
        source_channel_id=slash["channel"],
        initiatief_id=world.res["initiatief"],
        proposed_title="Gemeente",
        match_existing_lead_id=world.res["lead"],
        status="pending",
    )
    world.db.add(suggested)
    await world.db.flush()
    ctx = await perm_ctx(world, who)
    decision = await can(
        world.db, ctx, "suggested_lead:update", "suggested_lead", suggested.id
    )
    assert decision is allowed
    service = MattermostSlashService(world.db)
    context = {"suggested_lead_id": str(suggested.id)}
    with patch.object(MattermostSlashService, "_update_thread_post", AsyncMock()):
        result = await service.handle_action(slash["mm"][who], action, context)
    assert (result["ephemeral_text"] != _NO_WRITE) is allowed, result
    assert (suggested.status != "pending") is allowed
