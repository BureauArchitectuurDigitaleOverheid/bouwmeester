"""Deleting a record never removes or orphans what the caller has no rights on.

``core.deletion`` is the one rule every DELETE of a node, task, opdracht,
initiatief or lead goes through.  The inventory tests keep its table of
foreign keys complete and in line with the live schema and the ORM; the
route tests are the known cases of round 7.
"""

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import ONETOMANY

from bouwmeester.core.database import Base
from bouwmeester.core.deletion import (
    _FK_RULES,
    Detach,
    reachable_tables,
    referencing_fks,
)
from bouwmeester.models.github_link import GitHubLink
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.initiatief_update import InitiatiefUpdatePost
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_activity import LeadActivity
from bouwmeester.models.lead_column import LeadColumn
from bouwmeester.models.lead_node import LeadNode
from bouwmeester.models.mattermost_channel_link import MattermostChannelLink
from bouwmeester.models.mattermost_post_link import MattermostPostLink
from bouwmeester.models.mention import Mention
from bouwmeester.models.opdracht import Opdracht, OpdrachtNode
from bouwmeester.models.parlementair_abonnement import ParlementairAbonnement
from bouwmeester.models.parlementair_item import ParlementairItem, SuggestedEdge
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.signaalcontext import Signaalcontext
from bouwmeester.models.stakeholder_assessment import StakeholderAssessment
from bouwmeester.models.task import Task
from tests.authz_world import World, make_item
from tests.factories import client_as

ROOTS = ("corpus_node", "task", "opdracht", "initiatief", "lead")


# ---------------------------------------------------------------------------
# Inventory: every cascade and SET NULL is decided, and matches the schema
# ---------------------------------------------------------------------------

_DELETE_RULE = {"c": "CASCADE", "n": "SET NULL", "a": None, "r": None, "d": None}


async def _live_fks(db) -> dict[tuple[str, str], tuple[str, str | None]]:
    rows = await db.execute(
        text(
            """
            SELECT cl.relname, a.attname, pcl.relname, c.confdeltype::text
            FROM pg_constraint c
            JOIN pg_class cl ON cl.oid = c.conrelid
            JOIN pg_class pcl ON pcl.oid = c.confrelid
            JOIN pg_namespace n ON n.oid = cl.relnamespace
            JOIN pg_attribute a
              ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
            WHERE c.contype = 'f' AND n.nspname = 'public'
            """
        )
    )
    return {(r[0], r[1]): (r[2], _DELETE_RULE[r[3]]) for r in rows.all()}


async def test_every_fk_into_a_deletable_table_has_a_rule(db_session):
    """Lists every CASCADE / SET NULL foreign key a delete can reach.

    A new foreign key into one of these tables must be decided in
    ``core.deletion._FK_RULES``: part, owned, link or detach.
    """
    reach = reachable_tables(ROOTS)
    live = await _live_fks(db_session)
    missing = sorted(
        f"{child}.{col} -> {parent} ({rule})"
        for (child, col), (parent, rule) in live.items()
        if parent in reach and (child, col) not in _FK_RULES
    )
    assert not missing, missing


async def test_rules_match_the_live_delete_behaviour(db_session):
    """Detach only on SET NULL; part, owned and link only on CASCADE."""
    live = await _live_fks(db_session)
    wrong = []
    for (child, col), rule in _FK_RULES.items():
        assert (child, col) in live, f"{child}.{col} is not a foreign key"
        expected = "SET NULL" if isinstance(rule, Detach) else "CASCADE"
        if live[(child, col)][1] != expected:
            wrong.append((child, col, live[(child, col)][1], rule))
    assert not wrong, wrong


def test_models_declare_the_same_foreign_keys():
    for table in reachable_tables(ROOTS):
        for child, col in referencing_fks(table):
            assert (child.name, col.name) in _FK_RULES, (child.name, col.name)


def test_orm_relationships_follow_the_database():
    """No ORM relationship nulls a column the database would cascade.

    A one-to-many relationship without a delete cascade makes the ORM set
    the child's foreign key to NULL before the parent row goes: the child
    then survives without its scope (``Initiatief.leads`` left leads behind
    tenant-wide).
    """
    reach = reachable_tables(ROOTS)
    wrong = []
    for mapper in Base.registry.mappers:
        if mapper.local_table.name not in reach:
            continue
        for rel in mapper.relationships:
            if rel.direction is not ONETOMANY or rel.viewonly:
                continue
            ondelete = {fk.ondelete for c in rel.remote_side for fk in c.foreign_keys}
            if (
                ondelete == {"CASCADE"}
                and "delete" not in rel.cascade
                and rel.passive_deletes != "all"
            ):
                wrong.append(f"{mapper.class_.__name__}.{rel.key}")
    assert not wrong, wrong


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _count(db, model, *where) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(*where))


async def _delete(w: World, who: str, path: str):
    async with client_as(w.db, w.person[who]) as c:
        return await c.delete(path.format(**w.res))


def _scoped_rows(scope_type: str, scope_id: uuid.UUID) -> list:
    """One row of every polymorphic table that points at an initiatief/lead."""
    post_id = uuid.uuid4().hex[:26]
    return [
        MattermostChannelLink(
            channel_id=uuid.uuid4().hex[:26],
            channel_name="kanaal",
            channel_display_name="Kanaal",
            scope_type=scope_type,
            scope_id=scope_id,
        ),
        MattermostPostLink(
            post_id=post_id,
            channel_id=uuid.uuid4().hex[:26],
            scope_type=scope_type,
            scope_id=scope_id,
        ),
        ParlementairAbonnement(
            scope_type=scope_type,
            scope_id=scope_id,
            term="Regelrecht",
            term_genormaliseerd=f"regelrecht-{post_id}",
        ),
        GitHubLink(
            scope_type=scope_type,
            scope_id=scope_id,
            url=f"https://github.com/o/r/pull/{post_id}",
            link_type="pull_request",
            owner="o",
            repo="r",
        ),
        Signaalcontext(scope_type=scope_type, scope_id=scope_id, tekst="context"),
    ]


_SCOPED_MODELS = (
    MattermostChannelLink,
    MattermostPostLink,
    ParlementairAbonnement,
    GitHubLink,
    Signaalcontext,
)


async def _scoped_left(db, scope_type: str, scope_id: uuid.UUID) -> dict[str, int]:
    left = {}
    for model in _SCOPED_MODELS:
        n = await _count(
            db, model, model.scope_type == scope_type, model.scope_id == scope_id
        )
        if n:
            left[model.__tablename__] = n
    n = await _count(
        db,
        ResourcePermission,
        ResourcePermission.resource_type == scope_type,
        ResourcePermission.resource_id == scope_id,
    )
    if n:
        left["resource_permission"] = n
    return left


# ---------------------------------------------------------------------------
# 1. Node: tasks, opdrachten and links elsewhere block
# ---------------------------------------------------------------------------


@pytest.fixture
async def node_with_work_elsewhere(world: World) -> World:
    """The tenant-wide node carries a task and an opdracht of ``elders``."""
    db = world.db
    task = Task(
        title="Taak elders op vrije node",
        node_id=world.res["node_free"],
        organisatie_eenheid_id=world.org["elders"].id,
        status="open",
    )
    opdracht = Opdracht(
        type="opdracht",
        titel="Opdracht elders",
        begrotingsjaar=2026,
        opdrachtgever_id=world.org["elders"].id,
        instrument_id=world.res["node_free"],
    )
    db.add_all([task, opdracht])
    await db.flush()
    world.res.update(task_free_elders=task.id, opdracht_free_elders=opdracht.id)
    return world


async def test_node_delete_refuses_to_wipe_work_of_other_units(
    node_with_work_elsewhere,
):
    w = node_with_work_elsewhere
    # The directie manager holds node:delete, tenant-wide for a node without
    # eenheid, but has no rights in ``elders``.
    resp = await _delete(w, "manager", "/api/nodes/{node_free}")
    assert resp.status_code == 409, resp.text
    assert "1 taak" in resp.json()["detail"]
    assert "1 opdracht" in resp.json()["detail"]
    assert await w.db.get(Task, w.res["task_free_elders"]) is not None
    assert await w.db.get(Opdracht, w.res["opdracht_free_elders"]) is not None


async def test_node_delete_by_someone_who_may_delete_everything(
    node_with_work_elsewhere,
):
    w = node_with_work_elsewhere
    resp = await _delete(w, "super_admin", "/api/nodes/{node_free}")
    assert resp.status_code == 204, resp.text
    w.db.expire_all()
    assert await _count(w.db, Task, Task.id == w.res["task_free_elders"]) == 0
    assert (
        await _count(w.db, Opdracht, Opdracht.id == w.res["opdracht_free_elders"]) == 0
    )


async def test_node_delete_takes_own_work_and_removes_grants(world: World):
    """Tasks the caller may delete go with the node; grants, assessments and
    mentions of the node are removed, not orphaned."""
    db = world.db
    node_id = world.res["node_directie"]
    db.add_all(
        [
            StakeholderAssessment(
                person_id=world.person["viewer"].id,
                scope_type="corpus_node",
                scope_id=node_id,
            ),
            Mention(
                source_type="task",
                source_id=world.res["task_team"],
                mention_type="node",
                target_id=node_id,
            ),
        ]
    )
    await db.flush()
    resp = await _delete(world, "manager", "/api/nodes/{node_directie}")
    assert resp.status_code == 204, resp.text
    db.expire_all()
    assert await _count(db, Task, Task.id == world.res["task_team"]) == 0
    assert (
        await _count(
            db,
            ResourcePermission,
            ResourcePermission.resource_type == "corpus_node",
            ResourcePermission.resource_id == node_id,
        )
        == 0
    )
    assert (
        await _count(
            db, StakeholderAssessment, StakeholderAssessment.scope_id == node_id
        )
        == 0
    )
    assert await _count(db, Mention, Mention.target_id == node_id) == 0


async def test_node_delete_refuses_links_of_records_the_caller_may_not_change(
    world: World,
):
    """A lead's or opdracht's link to the node is theirs to lose."""
    db = world.db
    other = Initiatief(id=uuid.uuid4(), naam=f"Ander {uuid.uuid4().hex[:6]}")
    db.add(other)
    await db.flush()
    lead = Lead(title="Lead elders", stage="verkennen", initiatief_id=other.id)
    opdracht = Opdracht(
        type="opdracht",
        titel="Opdracht elders",
        begrotingsjaar=2026,
        opdrachtgever_id=world.org["elders"].id,
    )
    db.add_all([lead, opdracht])
    await db.flush()
    db.add_all(
        [
            LeadNode(lead_id=lead.id, node_id=world.res["node_directie"]),
            OpdrachtNode(opdracht_id=opdracht.id, node_id=world.res["node_directie"]),
        ]
    )
    await db.flush()

    resp = await _delete(world, "manager", "/api/nodes/{node_directie}")
    assert resp.status_code == 409, resp.text
    assert "1 lead" in resp.json()["detail"]
    assert "1 opdracht" in resp.json()["detail"]
    assert await _count(db, LeadNode, LeadNode.lead_id == lead.id) == 1


async def test_node_delete_takes_the_suggested_edges_of_its_item(world: World):
    """Without its node an item's suggestions would fall to anyone holding
    parlementair:review: they go with the node, the item stays."""
    item = await make_item(world, "node_team")
    world.db.add(
        SuggestedEdge(
            parlementair_item_id=item.id,
            target_node_id=world.res["node_elders"],
            edge_type_id=world.res["edge_type"],
            confidence=0.9,
        )
    )
    await world.db.flush()
    item_id = item.id
    resp = await _delete(world, "manager", "/api/nodes/{node_team}")
    assert resp.status_code == 204, resp.text
    world.db.expire_all()
    assert (
        await _count(
            world.db, SuggestedEdge, SuggestedEdge.parlementair_item_id == item_id
        )
        == 0
    )
    kept = await world.db.execute(
        select(ParlementairItem.corpus_node_id).where(ParlementairItem.id == item_id)
    )
    assert kept.one() == (None,)


# ---------------------------------------------------------------------------
# 2. Initiatief: its leads and everything scoped to it go with it
# ---------------------------------------------------------------------------


@pytest.fixture
async def full_initiatief(iw: World) -> World:
    db = iw.db
    init_id, lead_id = iw.res["initiatief"], iw.res["lead"]
    db.add_all(
        [
            *_scoped_rows("initiatief", init_id),
            *_scoped_rows("lead", lead_id),
            StakeholderAssessment(
                person_id=iw.person["viewer"].id,
                scope_type="initiatief",
                scope_id=init_id,
            ),
            InitiatiefUpdatePost(initiatief_id=init_id, titel="Update", body="x"),
            LeadActivity(lead_id=lead_id, content="Gesprek", activity_type="note"),
            ResourcePermission(
                person_id=iw.person["viewer"].id,
                resource_type="lead",
                resource_id=lead_id,
                rol="contactpersoon",
            ),
        ]
    )
    await db.flush()
    return iw


async def test_initiatief_delete_leaves_nothing_behind(full_initiatief):
    w = full_initiatief
    init_id, lead_id = w.res["initiatief"], w.res["lead"]
    resp = await _delete(w, "afd_editor", "/api/initiatieven/{initiatief}")
    assert resp.status_code == 204, resp.text
    w.db.expire_all()

    # The lead is gone, not left behind without initiatief.
    assert await _count(w.db, Lead, Lead.id == lead_id) == 0
    assert await _count(w.db, LeadActivity, LeadActivity.lead_id == lead_id) == 0
    assert await _scoped_left(w.db, "initiatief", init_id) == {}
    assert await _scoped_left(w.db, "lead", lead_id) == {}
    for model, column in (
        (LeadColumn, LeadColumn.initiatief_id),
        (InitiatiefUpdatePost, InitiatiefUpdatePost.initiatief_id),
    ):
        assert await _count(w.db, model, column == init_id) == 0
    assert (
        await _count(
            w.db, StakeholderAssessment, StakeholderAssessment.scope_id == init_id
        )
        == 0
    )
    # _scoped_left covers the channel links and abonnementen: no alert keeps
    # going to a channel of a deleted initiatief or lead.


async def test_team_viewer_gains_nothing_from_a_deleted_initiatief(full_initiatief):
    w = full_initiatief
    resp = await _delete(w, "afd_editor", "/api/initiatieven/{initiatief}")
    assert resp.status_code == 204, resp.text
    async with client_as(w.db, w.person["viewer"]) as c:
        assert (await c.get(f"/api/leads/{w.res['lead']}")).status_code == 404
        listed = (await c.get("/api/leads")).json()
    assert str(w.res["lead"]) not in {i["id"] for i in listed}


async def test_initiatief_delete_still_needs_initiatief_delete(full_initiatief):
    resp = await _delete(full_initiatief, "viewer", "/api/initiatieven/{initiatief}")
    assert resp.status_code in (403, 404)
    assert await full_initiatief.db.get(Lead, full_initiatief.res["lead"]) is not None


# ---------------------------------------------------------------------------
# 3. Task: subtasks the caller may not delete block
# ---------------------------------------------------------------------------


async def test_task_delete_refuses_subtasks_of_other_units(world: World):
    db = world.db
    sub = Task(
        title="Subtaak elders",
        node_id=world.res["node_elders"],
        organisatie_eenheid_id=world.org["elders"].id,
        parent_id=world.res["task_team"],
        status="open",
    )
    db.add(sub)
    await db.flush()

    resp = await _delete(world, "team_editor", "/api/tasks/{task_team}")
    assert resp.status_code == 409, resp.text
    assert "1 taak" in resp.json()["detail"]
    assert await db.get(Task, sub.id) is not None

    resp = await _delete(world, "super_admin", "/api/tasks/{task_team}")
    assert resp.status_code == 204, resp.text
    db.expire_all()
    assert await _count(db, Task, Task.id == sub.id) == 0


async def test_task_delete_takes_own_subtasks(world: World):
    db = world.db
    sub = Task(
        title="Eigen subtaak",
        node_id=world.res["node_directie"],
        organisatie_eenheid_id=world.org["team"].id,
        parent_id=world.res["task_team"],
        status="open",
    )
    db.add(sub)
    await db.flush()
    resp = await _delete(world, "team_editor", "/api/tasks/{task_team}")
    assert resp.status_code == 204, resp.text
    db.expire_all()
    assert await _count(db, Task, Task.id == sub.id) == 0


# ---------------------------------------------------------------------------
# 4. Opdracht and lead: grants, koppelingen and scoped rows go, tasks stay
# ---------------------------------------------------------------------------


async def test_opdracht_delete_removes_grants_and_koppelingen(world: World):
    db = world.db
    opdracht_id = world.res["opdracht_directie"]
    task = Task(
        title="Taak voor opdracht",
        node_id=world.res["node_directie"],
        organisatie_eenheid_id=world.org["directie"].id,
        opdracht_id=opdracht_id,
        status="open",
    )
    db.add_all(
        [
            task,
            OpdrachtNode(opdracht_id=opdracht_id, node_id=world.res["node_elders"]),
            ResourcePermission(
                person_id=world.person["viewer"].id,
                resource_type="opdracht",
                resource_id=opdracht_id,
                rol="betrokken",
            ),
        ]
    )
    await db.flush()

    task_id = task.id
    resp = await _delete(world, "manager", "/api/opdrachten/{opdracht_directie}")
    assert resp.status_code == 204, resp.text
    db.expire_all()
    assert await _count(db, OpdrachtNode, OpdrachtNode.opdracht_id == opdracht_id) == 0
    assert (
        await _count(
            db,
            ResourcePermission,
            ResourcePermission.resource_type == "opdracht",
            ResourcePermission.resource_id == opdracht_id,
        )
        == 0
    )
    # The task lives on its node and eenheid: it stays, without the opdracht.
    kept = await db.execute(select(Task.opdracht_id).where(Task.id == task_id))
    assert kept.one() == (None,)


async def test_lead_delete_removes_everything_scoped_to_it(iw: World):
    db = iw.db
    lead_id = iw.res["lead"]
    db.add_all(
        [
            *_scoped_rows("lead", lead_id),
            LeadActivity(lead_id=lead_id, content="Gesprek", activity_type="note"),
            ResourcePermission(
                person_id=iw.person["viewer"].id,
                resource_type="lead",
                resource_id=lead_id,
                rol="contactpersoon",
            ),
        ]
    )
    await db.flush()
    resp = await _delete(iw, "afd_editor", "/api/leads/{lead}")
    assert resp.status_code == 204, resp.text
    db.expire_all()
    assert await _count(db, Lead, Lead.id == lead_id) == 0
    assert await _scoped_left(db, "lead", lead_id) == {}


async def test_lead_merge_leaves_nothing_pointing_at_the_source(iw: World):
    """Merging deletes the source: its channel links and abonnementen go too."""
    db = iw.db
    target = Lead(title="Doel", stage="verkennen", initiatief_id=iw.res["initiatief"])
    db.add(target)
    await db.flush()
    source_id, target_id = iw.res["lead"], target.id
    db.add_all(_scoped_rows("lead", source_id))
    await db.flush()
    async with client_as(db, iw.person["afd_editor"]) as c:
        resp = await c.post(
            "/api/leads/merge",
            json={"source_id": str(source_id), "target_id": str(target_id)},
        )
    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert await _count(db, Lead, Lead.id == source_id) == 0
    assert await _scoped_left(db, "lead", source_id) == {}
