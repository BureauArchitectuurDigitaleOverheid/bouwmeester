"""Responses name nothing the caller cannot read.

Uses ``world`` from ``tests/authz_world.py``.  The team members (``viewer``,
``team_editor``) and the afdeling editor see up their line but not
``Elders``: ``Dossier elders`` and everything placed there is hidden from
them.  ``hw`` puts references to hidden things inside things they do read;
each check asks that the response leaves them out, and that a reader who
may see them still gets them.
"""

import json
import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import select

from bouwmeester.core.authz import org_visibility
from bouwmeester.models.activity import Activity
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge
from bouwmeester.models.edge_type import EdgeType
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_node import LeadNode
from bouwmeester.models.mattermost_channel_link import MattermostChannelLink
from bouwmeester.models.opdracht import Opdracht, OpdrachtNode
from bouwmeester.models.persoon_samenwerkingsverband import (
    PersoonSamenwerkingsverband,
)
from bouwmeester.models.task import Task
from bouwmeester.repositories.corpus_node import CorpusNodeRepository
from bouwmeester.services.llm.base import EdgeRelevanceResult
from bouwmeester.services.mattermost_slash_service import MattermostSlashService
from tests.authz_world import (
    World,
    add,
    add_directie_admin,
    chat_read,
    get_json,
    make_node,
    mm_account,
    opdracht,
    perm_ctx,
    request,
    rp,
    task,
)
from tests.factories import make_org, make_person, place

HIDDEN = "Dossier elders"
YESTERDAY = date.today() - timedelta(days=1)


@pytest.fixture
async def hw(world: World) -> World:
    db, org, res, p = world.db, world.org, world.res, world.person
    await add_directie_admin(world, "org_admin", "Directiebeheerder")  # scoped
    p["outsider"] = await make_person(db, "Buitenstaander")
    await place(db, p["outsider"], org["elders"])
    p["opdrachtgever"] = await make_person(db, "Opdrachtgever")
    await place(db, p["opdrachtgever"], await make_org(db, "Ver weg", "ministerie"))
    bridge = EdgeType(id=f"brug_{uuid.uuid4().hex[:8]}", label_nl="B", label_en="B")
    elders_opdracht = opdracht(world, "Opdracht elders", "elders")
    await add(world, bridge, elders_opdracht)
    (await db.get(Task, res["task_team"])).opdracht_id = elders_opdracht.id
    (await db.get(Opdracht, res["opdracht_directie"])).instrument_id = res[
        "node_elders"
    ]
    (await db.get(Lead, res["lead"])).assignee_id = p["viewer"].id
    res["init_naam"] = (await db.get(Initiatief, res["initiatief"])).naam
    lead, sub = res["lead"], {"parent_id": res["task_team"]}
    await add(
        world,
        # elders -> free: the only route from the team node to the free one
        Edge(from_node_id=res["node_elders"], to_node_id=res["node_free"],
             edge_type_id=bridge.id),
        task(world, "Zichtbare subtaak", "node_team", "team", **sub),
        task(world, "Subtaak elders", "node_elders", "elders", **sub),
        task(world, "Losse taak elders", "node_elders"),
        task(world, "Mijn taak elders", "node_elders", "elders",
             assignee_id=p["viewer"].id),
        OpdrachtNode(opdracht_id=res["opdracht_directie"], node_id=res["node_elders"]),
        OpdrachtNode(opdracht_id=res["opdracht_directie"], node_id=res["node_team"]),
        LeadNode(lead_id=lead, node_id=res["node_elders"]),
        LeadNode(lead_id=lead, node_id=res["node_afdeling"]),
        rp("corpus_node", res["node_elders"], "betrokken", person=p["role_only"]),
        rp("lead", lead, "contactpersoon", person=p["viewer"]),
        rp("lead", lead, "betrokken", eenheid=org["team"]),
        rp("lead", lead, "opdrachtgever", person=p["platform_admin"]),
        rp("lead", lead, "opdrachtgever", person=p["opdrachtgever"]),
        PersoonSamenwerkingsverband(
            person_id=p["viewer"].id,
            samenwerkingsverband_id=res["samenwerkingsverband"],
            start_datum=YESTERDAY,
        ),
    )  # fmt: skip
    return world


# ---------------------------------------------------------------------------
# REST responses leave out what the caller cannot read
# ---------------------------------------------------------------------------

_SUBS = ("Subtaak elders", "Opdracht elders")  # a task's subtask and opdracht
_OVERVIEW = "/api/tasks/eenheid-overview?organisatie_eenheid_id={eenheid_team}"
_COMMUNITY = "/api/graph/community?initiatief_id={initiatief}"
_PERMS = "/api/resource-permissions/by-person/{p_role_only}"

# (who, GET route, texts left out, texts that must be there)
REDACTED = [
    ("viewer", _PERMS, (HIDDEN,), ("Directiedossier",)),
    ("super_admin", _PERMS, (), (HIDDEN,)),
    # an opdracht's instrument and node koppelingen
    ("viewer", "/api/opdrachten/{opdracht_directie}", (HIDDEN,), ("Teamdossier",)),
    ("viewer", "/api/nodes/{node_team}/opdrachten", (HIDDEN,), ("Teamdossier",)),
    ("super_admin", "/api/opdrachten/{opdracht_directie}", (), (HIDDEN,)),
    # a task's subtasks and opdracht, in details, lists and the overview
    ("viewer", "/api/tasks/{task_team}", _SUBS, ("Zichtbare subtaak",)),
    ("viewer", "/api/nodes/{node_directie}/tasks", _SUBS, ("Zichtbare subtaak",)),
    ("viewer", "/api/tasks?organisatie_eenheid_id={eenheid_team}", _SUBS,
     ("Zichtbare subtaak",)),
    ("viewer", "/api/tasks", _SUBS, ("Zichtbare subtaak",)),
    ("super_admin", "/api/tasks/{task_team}", (), _SUBS),
    ("viewer", _OVERVIEW, (*_SUBS, "Losse taak elders"),
     ("Zichtbare subtaak", "Taak zonder eenheid", '"unassigned_no_unit_count":1')),
    # an own task on a hidden node keeps the node's id, not the node
    ("viewer", "/api/tasks/my", (HIDDEN,), ("Mijn taak elders", "{node_elders}")),
    # a lead's linked nodes, and its initiatief for a reader of the lead only
    ("afd_editor", "/api/leads/{lead}", (HIDDEN,), ("Afdelingsdossier",)),
    ("opdrachtgever", "/api/leads/{lead}", ("{init_naam}",),
     ('"initiatief":null', "{initiatief}")),
    ("opdrachtgever", "/api/leads", ("{init_naam}",), ("{initiatief}",)),
    ("afd_editor", "/api/leads", (), ("{init_naam}",)),
    # a node's edges to hidden nodes, counted too
    ("viewer", "/api/nodes/{node_directie}", ("{edge_directie_elders}",),
     ("{edge_team_directie}", '"edge_count":1')),
    ("super_admin", "/api/nodes/{node_directie}", (), ('"edge_count":2',)),
    # the community graph: people need people:read, verbanden their read
    ("role_only", _COMMUNITY, ("Teamlid",), ('"node_type":"lead"',)),
    ("afd_editor", _COMMUNITY, ("person-None",), ("Teamlid", "Werkgroep")),
    ("platform_admin", _COMMUNITY, ("Werkgroep",), ('"node_type":"lead"',)),
    # graph endpoints
    ("viewer", "/api/graph/search", (HIDDEN,), ("Teamdossier",)),
    ("super_admin", "/api/graph/search", (), (HIDDEN,)),
    ("viewer", "/api/nodes/{node_directie}/neighbors", (HIDDEN,), ("Teamdossier",)),
]  # fmt: skip


@pytest.mark.parametrize(
    ("who", "path", "hidden", "shown"),
    REDACTED,
    ids=[f"{r[0]}-{r[1].split('?')[0]}" for r in REDACTED],
)
async def test_responses_leave_out_what_the_caller_cannot_read(
    hw, who, path, hidden, shown
):
    resp = await request(hw, who, "GET", path)
    assert resp.status_code == 200, resp.text
    for text in hw.fill(list(hidden)):
        assert text not in resp.text, text
    for text in hw.fill(list(shown)):
        assert text in resp.text, text


async def test_graph_edges_only_join_drawn_nodes(hw):
    search = await get_json(hw, "viewer", "/api/graph/search")
    ids = {n["id"] for n in search["nodes"]}
    assert str(hw.res["node_team"]) in ids
    assert all({e["from_node_id"], e["to_node_id"]} <= ids for e in search["edges"])
    graph = await get_json(hw, "afd_editor", _COMMUNITY)
    ids = {n["id"] for n in graph["nodes"]}
    assert all({e["source"], e["target"]} <= ids for e in graph["edges"])
    # a lead role held by an eenheid is drawn to that eenheid
    lead, team = f"lead-{hw.res['lead']}", f"oe-{hw.org['team'].id}"
    assert any((e["source"], e["target"]) == (lead, team) for e in graph["edges"])


# (who, from, to, the titles on the path)
PATHS = [
    ("viewer", "node_team", "node_free", []),  # only through Elders
    ("viewer", "node_team", "node_elders", []),
    ("viewer", "node_team", "node_directie", ["Teamdossier", "Directiedossier"]),
    ("super_admin", "node_team", "node_free",
     ["Teamdossier", "Directiedossier", HIDDEN, "Dossier zonder eenheid"]),
]  # fmt: skip


@pytest.mark.parametrize(("who", "start", "end", "titles"), PATHS)
async def test_graph_path_runs_only_through_visible_nodes(hw, who, start, end, titles):
    params = {"from_id": hw.res[start], "to_id": hw.res[end]}
    steps = (await get_json(hw, who, "/api/graph/path", **params))["path"]
    assert [s["node_title"] for s in steps] == titles
    if who == "viewer" and titles:
        edge = str(hw.res["edge_team_directie"])
        assert [s["edge_id"] for s in steps] == [None, edge]
    chat = json.loads(
        await chat_read(hw, who, "find_path", from_node_id=hw.res[start],
                        to_node_id=hw.res[end])
    )  # fmt: skip
    assert (chat["path"] == []) is (not titles)


@pytest.mark.parametrize("who", ["viewer", "super_admin"])
async def test_subgraph_does_not_walk_through_hidden_nodes(hw, who):
    body = await get_json(hw, who, "/api/nodes/{node_team}/graph", depth=5)
    titles = {n["title"] for n in body["nodes"]}
    if who == "viewer":  # the free node is visible, but only reachable via Elders
        assert titles == {"Teamdossier", "Directiedossier"}
        assert len(body["edges"]) == 1
    else:
        assert {HIDDEN, "Dossier zonder eenheid"} <= titles


async def test_reordering_subtasks_covers_only_visible_ones(hw):
    subs = {
        t.title: str(t.id)
        for t in await hw.db.scalars(
            select(Task).where(Task.parent_id == hw.res["task_team"])
        )
    }
    url = "/api/tasks/{task_team}/subtasks/reorder"
    ok = await request(hw, "team_editor", "PUT", url,
                       {"task_ids": [subs["Zichtbare subtaak"]]})  # fmt: skip
    assert ok.status_code == 200, ok.text
    assert [t["title"] for t in ok.json()] == ["Zichtbare subtaak"]
    # a hidden subtask is not one of "your" subtasks; no count is told either
    for ids in (list(subs.values()), []):
        refused = await request(hw, "team_editor", "PUT", url, {"task_ids": ids})
        assert refused.status_code == 400, refused.text
        assert subs["Subtaak elders"] not in refused.text
        assert not {"1", "2"} & set(refused.json()["detail"])


# ---------------------------------------------------------------------------
# Chat read tools and the audit log
# ---------------------------------------------------------------------------

# (who, tool, args, texts left out, texts that must be there)
CHAT = [
    ("viewer", "get_node", {"node_id": "{node_elders}"}, (HIDDEN,), ('"error"',)),
    ("viewer", "get_node", {"node_id": "{node_team}"}, (), ("Teamdossier",)),
    ("viewer", "get_node_neighbors", {"node_id": "{node_directie}"}, (HIDDEN,),
     ("Teamdossier",)),
    ("viewer", "get_node_neighbors", {"node_id": "{node_elders}"},
     ("Directiedossier",), ('"error"',)),
    ("viewer", "find_similar_nodes", {"title": HIDDEN}, (HIDDEN,), ()),
    ("super_admin", "find_similar_nodes", {"title": HIDDEN}, (), (HIDDEN,)),
]  # fmt: skip


@pytest.mark.parametrize(("who", "tool", "args", "hidden", "shown"), CHAT)
async def test_chat_read_tools_leave_out_hidden_nodes(
    hw, who, tool, args, hidden, shown
):
    result = await chat_read(hw, who, tool, **args)
    assert not [t for t in hidden if t in result], result
    assert all(t in result for t in shown), result


async def test_chat_get_opdracht_reads_like_opdracht_read(world):
    """Visible through either eenheid; a hidden one answers as a missing one."""
    team = world.org["team"].id
    for_team, secret = await add(
        world,
        opdracht(world, "Uitvoering door het team", "elders",
                 opdrachtnemer_eenheid_id=team),
        opdracht(world, "Geheime opdracht", "elders",
                 opdrachtnemer_eenheid_id=world.org["elders"].id),
    )  # fmt: skip
    seen = await chat_read(world, "viewer", "get_opdracht", opdracht_id=for_team.id)
    refused = await chat_read(world, "viewer", "get_opdracht", opdracht_id=secret.id)
    missing = await chat_read(world, "viewer", "get_opdracht", opdracht_id=uuid.uuid4())
    assert json.loads(seen)["titel"] == "Uitvoering door het team"
    assert refused == missing and "Geheime opdracht" not in refused


# (tool, args, REST twin)
READ_TOOL_TWINS = [
    ("search_people", {"query": "Team"}, "/api/people/search?q=Team"),
    ("get_person_summary", {"person_id": "{p_viewer}"},
     "/api/people/{p_viewer}/summary"),
    ("list_parlementair", {}, "/api/parlementair/imports"),
]  # fmt: skip


@pytest.mark.parametrize("who", ["role_only", "viewer"])
@pytest.mark.parametrize(("tool", "args", "twin"), READ_TOOL_TWINS)
async def test_chat_read_tool_is_gated_like_its_rest_twin(world, who, tool, args, twin):
    rest_allowed = (await request(world, who, "GET", twin)).status_code == 200
    result = json.loads(await chat_read(world, who, tool, **args))
    assert ("error" not in result) is rest_allowed
    # role_only holds no role at all: every one of these is refused
    assert rest_allowed is (who == "viewer")


@pytest.mark.parametrize(
    ("who", "allowed"),
    [("viewer", False), ("org_admin", False), ("platform_admin", True)],
)
async def test_audit_log_needs_a_system_role(hw, who, allowed):
    """The log is tenant-wide: audit:read scoped to a directie is not enough."""
    feed = await request(hw, who, "GET", "/api/activity/feed")
    assert feed.status_code == (200 if allowed else 403), feed.text
    chat = json.loads(await chat_read(hw, who, "get_recent_activity"))
    assert ("activities" in chat) is allowed, chat


# ---------------------------------------------------------------------------
# Slash commands, the inbox, a person summary
# ---------------------------------------------------------------------------

# (who, command, on the linked channel?, texts that must be there, left out)
SLASH = [
    ("viewer", "status elders", False, ("Geen dossier gevonden",), ()),
    ("outsider", "status elders", False, ("{node_elders}",), ()),
    ("viewer", "status Directiedossier", False, ("Totaal taken: 1",), ()),
    ("super_admin", "status Directiedossier", False, ("Totaal taken: 2",), ()),
    ("outsider", "kanaal", True, (), ("{init_naam}",)),
    ("afd_editor", "kanaal", True, ("{init_naam}",), ()),
    ("viewer", "taken", False, ("Mijn teamtaak", "Teamdossier"), (HIDDEN,)),
]  # fmt: skip


@pytest.mark.parametrize(("who", "command", "linked", "shown", "hidden"), SLASH)
async def test_slash_commands_name_only_readable_things(
    hw, who, command, linked, shown, hidden
):
    viewer, channel = hw.person["viewer"].id, uuid.uuid4().hex[:26]
    await add(
        hw,
        task(hw, "Taak elders", "node_directie", "elders"),
        task(hw, "Mijn teamtaak", "node_elders", "team", assignee_id=viewer),
        task(hw, "Taak bij eigen dossier", "node_team", "team", assignee_id=viewer),
        MattermostChannelLink(channel_id=channel, channel_name="kanaal",
                              channel_display_name="kanaal", scope_type="initiatief",
                              scope_id=hw.res["initiatief"]),
    )  # fmt: skip
    text = (
        await MattermostSlashService(hw.db).handle_command(
            await mm_account(hw, who),
            command,
            channel_id=channel if linked else uuid.uuid4().hex[:26],
            channel_name="kanaal",
        )
    )["text"]
    assert all(t in text for t in hw.fill(list(shown))), text
    assert not [t for t in hw.fill(list(hidden)) if t in text], text


@pytest.mark.parametrize("path", ["/api/tasks/inbox", "/api/activity/inbox"])
async def test_inbox_names_only_readable_nodes(world, path):
    """An own task stays without its node; activity naming the node is left out."""
    viewer = world.person["viewer"].id
    own = task(
        world,
        "Mijn verlopen taak",
        "node_elders",
        "team",
        assignee_id=viewer,
        deadline=date.today() - timedelta(days=3),
    )
    await add(
        world,
        own,
        *(Activity(event_type="node.updated", actor_id=viewer, node_id=world.res[k],
                   details={"title": t})
          for k, t in (("node_elders", HIDDEN), ("node_team", "Teamdossier"))),
    )  # fmt: skip
    resp = await request(world, "viewer", "GET", path)
    assert resp.status_code == 200, resp.text
    assert HIDDEN not in resp.text
    assert str(world.res["node_elders"]) not in resp.text
    items = resp.json()["items"]
    overdue = [
        (i["related_task_id"], i["related_node_id"])
        for i in items
        if i["type"] == "overdue_task"
    ]
    assert overdue == [(str(own.id), None)]
    changes = [i["related_node_id"] for i in items if i["type"] == "node_change"]
    assert changes == [str(world.res["node_team"])]


async def test_person_summary_names_only_readable_tasks_and_nodes(world):
    colleague = world.person["collega"] = await make_person(world.db, "Collega")
    await place(world.db, colleague, world.org["elders"])
    await add(
        world,
        task(world, "Taak elders van collega", "node_elders", "elders",
             assignee_id=colleague.id),
        task(world, "Teamtaak van collega", "node_team", "team",
             assignee_id=colleague.id),
        rp("corpus_node", world.res["node_elders"], "betrokken", person=colleague),
        rp("corpus_node", world.res["node_team"], "betrokken", person=colleague),
    )  # fmt: skip
    body = await get_json(world, "viewer", f"/api/people/{colleague.id}/summary")
    assert [t["title"] for t in body["open_tasks"]] == ["Teamtaak van collega"]
    assert body["open_task_count"] == 1
    assert [n["node_title"] for n in body["stakeholder_nodes"]] == ["Teamdossier"]
    chat = await chat_read(
        world, "viewer", "get_person_summary", person_id=colleague.id
    )
    assert "Teamtaak van collega" in chat and "Taak elders" not in chat
    assert json.loads(chat)["aantal_open_taken"] == 1


# ---------------------------------------------------------------------------
# Counts and totals over the corpus
# ---------------------------------------------------------------------------


async def test_dashboard_counts_only_visible_listed_nodes(world):
    async def count(who: str) -> int:
        stats = await get_json(world, who, "/api/notifications/dashboard-stats")
        return stats["corpus_node_count"]

    viewer, admin = await count("viewer"), await count("super_admin")
    org_ctx = await org_visibility(world.db, await perm_ctx(world, "viewer"))
    assert viewer == await CorpusNodeRepository(world.db).count(org_ctx=org_ctx)
    await make_node(world.db, "Verborgen dossier", world.org["elders"])
    assert (await count("viewer"), await count("super_admin")) == (viewer, admin + 1)
    # what the node list hides by default is not counted either
    ended = await make_node(world.db, "Beeindigd dossier")
    ended.geldig_tot = date(2020, 1, 1)
    await add(world, CorpusNode(title="Motie", node_type="politieke_input",
                                status="actief"))  # fmt: skip
    assert await count("super_admin") == admin + 1


async def test_beleidskompas_and_gap_analysis_count_only_visible_children(world):
    """The team dossier has a visible probleem and a doel in Elders."""
    if await world.db.get(EdgeType, "onderdeel_van") is None:
        await add(world, EdgeType(id="onderdeel_van", label_nl="O", label_en="P"))
    probleem = await make_node(world.db, "Probleem", world.org["team"])
    doel = await make_node(world.db, "Doel elders", world.org["elders"])
    probleem.node_type, doel.node_type = "probleem", "doel"
    await add(world, *(
        Edge(from_node_id=n.id, to_node_id=world.res["node_team"],
             edge_type_id="onderdeel_van") for n in (probleem, doel)
    ))  # fmt: skip
    team = str(world.res["node_team"])
    for who, completed in (("viewer", 1), ("super_admin", 2)):
        nodes = await get_json(world, who, "/api/nodes", node_type="dossier", limit=500)
        [node] = [n for n in nodes if n["id"] == team]
        assert node["beleidskompas_progress"]["completed_steps"] == completed
        gap = await request(world, who, "POST", "/api/llm/gap-analysis",
                            {"dossier_id": team})  # fmt: skip
        assert gap.json()["completed_count"] == completed, gap.text
        overview = await get_json(world, who, "/api/llm/corpus-gaps")
        items = {i["dossier_id"]: i for i in overview["items"]}
        assert items[team]["completed_count"] == completed
        assert (str(world.res["node_elders"]) in items) is (who == "super_admin")


async def test_kompas_guidance_only_suggests_visible_nodes(world):
    prompted = []

    class FakeLLM:
        async def score_edge_relevance(self, *, target_title, **_):
            prompted.append(target_title)
            return EdgeRelevanceResult(
                score=0.9, suggested_edge_type="verwijst_naar", reason="past"
            )

    async def llm_for(*_a, **_k):
        return FakeLLM()

    for title, eenheid in (("Geheim instrument", "elders"), ("Teaminstrument", "team")):
        (await make_node(world.db, title, world.org[eenheid])).node_type = "instrument"
    await world.db.flush()
    body = {"dossier_id": "{node_team}", "step_node_types": ["instrument"],
            "max_candidates": 50}  # fmt: skip
    with patch("bouwmeester.api.routes.llm.get_llm_service_for", llm_for):
        resp = await request(world, "viewer", "POST", "/api/llm/kompas-guidance", body)
    assert resp.status_code == 200, resp.text
    titles = {s["target_node_title"] for s in resp.json()["suggestions"]}
    assert "Teaminstrument" in titles
    assert "Geheim instrument" not in titles | set(prompted)


async def test_financieel_skips_instruments_behind_a_hidden_node(world):
    """team -> instrument counts; team -> elders (hidden) -> instrument not."""
    instruments = {}
    for budget in (7, 5):
        node = await add(
            world, CorpusNode(title=f"Instr {budget}", node_type="instrument")
        )
        await add(world, opdracht(world, f"Opdracht {budget}", instrument_id=node.id,
                                  budget=Decimal(budget)))  # fmt: skip
        instruments[budget] = node.id
    team, elders = world.res["node_team"], world.res["node_elders"]
    await add(world, *(
        Edge(from_node_id=a, to_node_id=b, edge_type_id=world.res["edge_type"])
        for a, b in ((team, instruments[7]), (team, elders), (elders, instruments[5]))
    ))  # fmt: skip
    body = await get_json(world, "viewer", f"/api/nodes/{team}/financieel")
    assert Decimal(str(body["totaal_budget"])) == Decimal(7)
