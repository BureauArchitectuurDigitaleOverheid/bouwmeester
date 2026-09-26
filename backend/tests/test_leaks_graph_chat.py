"""Read leaks outside the core: graph endpoints, chat tools, slash commands.

Uses ``world`` from ``tests/authz_world.py``.  ``viewer`` sits in the
team and sees up its line (team, afdeling, directie, DG, ministerie) plus
nodes without an eenheid, but not ``Elders`` or the sibling team.  The
corpus has the edges team -> directie -> elders; ``bridge`` adds
elders -> free, so the only route from the team node to the free node runs
through an invisible node.
"""

import json
import uuid

import pytest

from bouwmeester.models.edge import Edge
from bouwmeester.models.edge_type import EdgeType
from tests.authz_world import World
from tests.factories import client_as, grant_role, make_person, place

INVISIBLE = "Dossier elders"


@pytest.fixture
async def bridge(world: World) -> World:
    et = EdgeType(id=f"brug_{uuid.uuid4().hex[:8]}", label_nl="B", label_en="B")
    world.db.add(et)
    await world.db.flush()
    world.db.add(
        Edge(
            from_node_id=world.res["node_elders"],
            to_node_id=world.res["node_free"],
            edge_type_id=et.id,
        )
    )
    await world.db.flush()
    return world


def _titles(nodes: list[dict]) -> set[str]:
    return {n["title"] for n in nodes}


# ---------------------------------------------------------------------------
# H1: graph endpoints
# ---------------------------------------------------------------------------


async def test_graph_search_hides_invisible_nodes_and_their_edges(bridge):
    async with client_as(bridge.db, bridge.person["viewer"]) as c:
        resp = await c.get("/api/graph/search")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = {n["id"] for n in body["nodes"]}
    assert str(bridge.res["node_elders"]) not in ids
    assert str(bridge.res["node_team"]) in ids
    for edge in body["edges"]:
        assert edge["from_node_id"] in ids and edge["to_node_id"] in ids


async def test_graph_search_shows_everything_to_super_admin(bridge):
    async with client_as(bridge.db, bridge.person["super_admin"]) as c:
        resp = await c.get("/api/graph/search")
    assert INVISIBLE in _titles(resp.json()["nodes"])


async def test_graph_path_does_not_run_through_invisible_nodes(bridge):
    params = {"from_id": bridge.res["node_team"], "to_id": bridge.res["node_free"]}
    async with client_as(bridge.db, bridge.person["viewer"]) as c:
        hidden = await c.get("/api/graph/path", params=params)
    async with client_as(bridge.db, bridge.person["super_admin"]) as c:
        full = await c.get("/api/graph/path", params=params)
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["path"] == []
    assert INVISIBLE not in hidden.text
    assert [s["node_title"] for s in full.json()["path"]] == [
        "Teamdossier",
        "Directiedossier",
        INVISIBLE,
        "Dossier zonder eenheid",
    ]


async def test_graph_path_to_an_invisible_node_is_empty(bridge):
    params = {"from_id": bridge.res["node_team"], "to_id": bridge.res["node_elders"]}
    async with client_as(bridge.db, bridge.person["viewer"]) as c:
        resp = await c.get("/api/graph/path", params=params)
    assert resp.json()["path"] == []


async def test_graph_path_between_visible_nodes(bridge):
    params = {"from_id": bridge.res["node_team"], "to_id": bridge.res["node_directie"]}
    async with client_as(bridge.db, bridge.person["viewer"]) as c:
        resp = await c.get("/api/graph/path", params=params)
    steps = resp.json()["path"]
    assert [s["node_title"] for s in steps] == ["Teamdossier", "Directiedossier"]
    assert steps[0]["edge_id"] is None
    assert steps[1]["edge_id"] == str(bridge.res["edge_team_directie"])


async def test_node_neighbors_hide_invisible_neighbours(bridge):
    async with client_as(bridge.db, bridge.person["viewer"]) as c:
        resp = await c.get(f"/api/nodes/{bridge.res['node_directie']}/neighbors")
    assert resp.status_code == 200, resp.text
    titles = {n["node"]["title"] for n in resp.json()["neighbors"]}
    assert titles == {"Teamdossier"}


async def test_node_subgraph_does_not_walk_through_invisible_nodes(bridge):
    async with client_as(bridge.db, bridge.person["viewer"]) as c:
        resp = await c.get(
            f"/api/nodes/{bridge.res['node_team']}/graph", params={"depth": 5}
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # The free node is visible, but only reachable through Elders.
    assert _titles(body["nodes"]) == {"Teamdossier", "Directiedossier"}
    assert len(body["edges"]) == 1


async def test_node_subgraph_for_super_admin_is_complete(bridge):
    async with client_as(bridge.db, bridge.person["super_admin"]) as c:
        resp = await c.get(
            f"/api/nodes/{bridge.res['node_team']}/graph", params={"depth": 5}
        )
    assert {INVISIBLE, "Dossier zonder eenheid"} <= _titles(resp.json()["nodes"])


# ---------------------------------------------------------------------------
# H2 / M9: chat read tools
# ---------------------------------------------------------------------------


async def _read(w: World, who: str, tool: str, **args) -> str:
    from bouwmeester.services.chat_service import _execute_read_tool

    return await _execute_read_tool(
        tool,
        {k: str(v) for k, v in args.items()},
        w.db,
        person_id=w.person[who].id,
    )


async def test_chat_get_node_refuses_an_invisible_node(bridge):
    hidden = json.loads(
        await _read(bridge, "viewer", "get_node", node_id=bridge.res["node_elders"])
    )
    seen = json.loads(
        await _read(bridge, "viewer", "get_node", node_id=bridge.res["node_team"])
    )
    assert "error" in hidden and INVISIBLE not in json.dumps(hidden)
    assert seen["title"] == "Teamdossier"


async def test_chat_get_opdracht_reads_like_opdracht_read(world):
    """Visible through either eenheid, like ``opdracht:read``; hidden is missing."""
    from bouwmeester.models.opdracht import Opdracht

    def _opdracht(titel: str, opdrachtnemer: str) -> Opdracht:
        return Opdracht(
            type="opdracht",
            titel=titel,
            begrotingsjaar=2026,
            opdrachtgever_id=world.org["elders"].id,
            opdrachtnemer_eenheid_id=world.org[opdrachtnemer].id,
        )

    for_team = _opdracht("Uitvoering door het team", "team")
    hidden = _opdracht("Geheime opdracht", "elders")
    world.db.add_all([for_team, hidden])
    await world.db.flush()
    seen = json.loads(
        await _read(world, "viewer", "get_opdracht", opdracht_id=for_team.id)
    )
    refused = await _read(world, "viewer", "get_opdracht", opdracht_id=hidden.id)
    missing = await _read(world, "viewer", "get_opdracht", opdracht_id=uuid.uuid4())
    assert seen["titel"] == "Uitvoering door het team"
    assert refused == missing
    assert "Geheime opdracht" not in refused


async def test_chat_neighbors_hide_invisible_neighbours(bridge):
    result = await _read(
        bridge, "viewer", "get_node_neighbors", node_id=bridge.res["node_directie"]
    )
    assert INVISIBLE not in result
    assert "Teamdossier" in result


async def test_chat_neighbors_of_an_invisible_node(bridge):
    result = await _read(
        bridge, "viewer", "get_node_neighbors", node_id=bridge.res["node_elders"]
    )
    assert "error" in json.loads(result)
    assert "Directiedossier" not in result


async def test_chat_find_path_does_not_run_through_invisible_nodes(bridge):
    result = await _read(
        bridge,
        "viewer",
        "find_path",
        from_node_id=bridge.res["node_team"],
        to_node_id=bridge.res["node_free"],
    )
    assert json.loads(result)["path"] == []
    assert INVISIBLE not in result


async def test_chat_find_similar_nodes_is_filtered(bridge):
    result = await _read(bridge, "viewer", "find_similar_nodes", title=INVISIBLE)
    admin = await _read(bridge, "super_admin", "find_similar_nodes", title=INVISIBLE)
    assert INVISIBLE not in result
    assert INVISIBLE in admin


# ---------------------------------------------------------------------------
# M11: the audit log is tenant-wide, so it needs a system role
# ---------------------------------------------------------------------------


@pytest.fixture
async def auditors(world: World) -> World:
    """A ministry_admin on the directie: audit:read, but scoped (as in the seed)."""
    scoped = await make_person(world.db, "Directeur met ministry_admin")
    await place(world.db, scoped, world.org["directie"])
    await grant_role(world.db, scoped, "ministry_admin", world.org["directie"])
    world.person["scoped_auditor"] = scoped
    return world


AUDIT_CASES = [("viewer", False), ("scoped_auditor", False), ("platform_admin", True)]


@pytest.mark.parametrize(("who", "allowed"), AUDIT_CASES)
async def test_audit_feed_needs_system_audit_read(auditors, who, allowed):
    async with client_as(auditors.db, auditors.person[who]) as c:
        resp = await c.get("/api/activity/feed")
    assert resp.status_code == (200 if allowed else 403), resp.text


@pytest.mark.parametrize(("who", "allowed"), AUDIT_CASES)
async def test_chat_recent_activity_needs_system_audit_read(auditors, who, allowed):
    result = json.loads(await _read(auditors, who, "get_recent_activity"))
    assert ("activities" in result) is allowed, result


async def test_chat_person_summary_counts_only_visible_tasks(bridge):
    from bouwmeester.models.task import Task

    assignee = bridge.person["afd_editor"]
    bridge.db.add_all(
        [
            Task(
                title="Zichtbare taak",
                node_id=bridge.res["node_team"],
                assignee_id=assignee.id,
                status="open",
            ),
            Task(
                title="Taak elders",
                node_id=bridge.res["node_elders"],
                organisatie_eenheid_id=bridge.org["elders"].id,
                assignee_id=assignee.id,
                status="open",
            ),
        ]
    )
    await bridge.db.flush()
    result = await _read(bridge, "viewer", "get_person_summary", person_id=assignee.id)
    assert "Zichtbare taak" in result
    assert "Taak elders" not in result
    assert json.loads(result)["aantal_open_taken"] == 1


# ---------------------------------------------------------------------------
# R-9: chat write tools place things where REST would
# ---------------------------------------------------------------------------


async def test_chat_create_lead_uses_a_placement_where_the_user_may_create(world):
    """The oldest placement has no lead:create; a later one does."""
    from datetime import date

    from bouwmeester.models.lead import Lead
    from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
    from bouwmeester.services.chat_service import _execute_write_tool

    person = await make_person(world.db, "Twee plaatsingen")
    world.db.add(
        PersonOrganisatieEenheid(
            person_id=person.id,
            organisatie_eenheid_id=world.org["elders"].id,
            start_datum=date(2020, 1, 1),
        )
    )
    await place(world.db, person, world.org["afdeling"])
    await grant_role(world.db, person, "editor", world.org["afdeling"])

    result = await _execute_write_tool(
        "create_lead", {"title": "Lead via chat"}, world.db, person_id=person.id
    )
    assert result["success"], result
    lead = await world.db.get(Lead, uuid.UUID(result["entity_id"]))
    assert lead.organisatie_eenheid_id == world.org["afdeling"].id


@pytest.mark.parametrize(("eenheid", "allowed"), [("team", True), ("elders", False)])
async def test_chat_create_task_in_an_eenheid_asks_that_eenheid(
    world, eenheid, allowed
):
    from bouwmeester.services.chat_service import _authorize_write_tool

    refusal = await _authorize_write_tool(
        "create_task",
        {
            "node_id": str(world.res["node_team"]),
            "title": "x",
            "organisatie_eenheid_id": str(world.org[eenheid].id),
        },
        world.db,
        world.person["team_editor"].id,
    )
    assert (refusal is None) is allowed, refusal


async def test_chat_add_tag_is_node_update(world):
    """Linking an existing tag needs node:update on the node, as in REST."""
    from bouwmeester.core.authz import can
    from bouwmeester.core.permissions import build_permission_context
    from bouwmeester.services.chat_service import _authorize_write_tool

    for who, person in world.person.items():
        ctx = await build_permission_context(world.db, person)
        for node in ("node_team", "node_directie", "node_elders"):
            refusal = await _authorize_write_tool(
                "add_tag_to_node",
                {"node_id": str(world.res[node]), "tag_name": "x"},
                world.db,
                person.id,
            )
            node_id = world.res[node]
            expected = await can(world.db, ctx, "node:update", "corpus_node", node_id)
            assert (refusal is None) is expected, (who, node)


# ---------------------------------------------------------------------------
# M8 / M11b: Mattermost slash commands
# ---------------------------------------------------------------------------


def _mm_id() -> str:
    return uuid.uuid4().hex[:26]


@pytest.fixture
async def mm(world: World) -> dict[str, str]:
    """A Mattermost account for everyone in ``world``, plus an outsider in Elders."""
    from bouwmeester.models.mattermost_user import MattermostUser

    outsider = await make_person(world.db, "Buitenstaander")
    await place(world.db, outsider, world.org["elders"])
    world.person["outsider"] = outsider
    ids = {}
    for who, person in world.person.items():
        ids[who] = _mm_id()
        world.db.add(
            MattermostUser(
                person_id=person.id,
                mattermost_user_id=ids[who],
                mattermost_username=who,
            )
        )
    await world.db.flush()
    return ids


async def _slash(w: World, mm_ids: dict, who: str, text: str, channel=None) -> str:
    from bouwmeester.services.mattermost_slash_service import MattermostSlashService

    result = await MattermostSlashService(w.db).handle_command(
        mm_ids[who], text, channel_id=channel or _mm_id(), channel_name="kanaal"
    )
    return result["text"]


async def test_slash_status_does_not_find_an_invisible_dossier(world, mm):
    hidden = await _slash(world, mm, "viewer", "status elders")
    seen = await _slash(world, mm, "outsider", "status elders")
    assert hidden.startswith("Geen dossier gevonden"), hidden
    assert str(world.res["node_elders"]) in seen


async def test_slash_status_counts_only_visible_tasks(world, mm):
    from bouwmeester.models.task import Task

    world.db.add(
        Task(
            title="Taak elders",
            node_id=world.res["node_directie"],
            organisatie_eenheid_id=world.org["elders"].id,
            status="open",
        )
    )
    await world.db.flush()
    viewer = await _slash(world, mm, "viewer", "status Directiedossier")
    admin = await _slash(world, mm, "super_admin", "status Directiedossier")
    assert "Totaal taken: 1" in viewer, viewer
    assert "Totaal taken: 2" in admin, admin


@pytest.fixture
async def linked_channel(world: World) -> str:
    from bouwmeester.models.mattermost_channel_link import MattermostChannelLink

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
    await world.db.flush()
    return channel


async def test_slash_kanaal_names_the_initiatief_only_to_who_sees_it(
    world, mm, linked_channel
):
    from bouwmeester.models.initiatief import Initiatief

    naam = (await world.db.get(Initiatief, world.res["initiatief"])).naam
    outsider = await _slash(world, mm, "outsider", "kanaal", linked_channel)
    member = await _slash(world, mm, "afd_editor", "kanaal", linked_channel)
    assert naam not in outsider
    assert naam in member


# (open channel?, member?, Mattermost reachable?, linked?)
KOPPEL_CASES = [
    (True, False, True, True),
    (False, True, True, True),
    (False, False, True, False),
    (False, True, False, False),
]


@pytest.mark.parametrize(("is_open", "member", "reachable", "linked"), KOPPEL_CASES)
async def test_slash_koppel_private_channel_needs_membership(
    world, mm, is_open, member, reachable, linked
):
    from unittest.mock import AsyncMock, patch

    from bouwmeester.models.initiatief import Initiatief
    from bouwmeester.repositories.mattermost_channel_link import (
        MattermostChannelLinkRepository,
    )
    from bouwmeester.services.mattermost_service import (
        MattermostService,
        MattermostUnavailableError,
    )

    naam = (await world.db.get(Initiatief, world.res["initiatief"])).naam
    channel = _mm_id()
    down = MattermostUnavailableError("weg")
    with (
        patch.object(
            MattermostService,
            "is_open_channel",
            AsyncMock(return_value=is_open, side_effect=None if reachable else down),
        ),
        patch.object(
            MattermostService, "is_member_of_channel", AsyncMock(return_value=member)
        ) as is_member,
    ):
        # role_only is contributor on the initiatief: may link it.
        await _slash(world, mm, "role_only", f"koppel initiatief {naam}", channel)
    link = await MattermostChannelLinkRepository(world.db).get_by_channel_id(channel)
    assert (link is not None) is linked
    if not is_open and reachable:
        assert is_member.await_args.args == (channel, mm["role_only"])
