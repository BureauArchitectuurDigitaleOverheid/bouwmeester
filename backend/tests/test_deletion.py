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

import tests.authz_world as aw
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

ROOTS = ("corpus_node", "task", "opdracht", "initiatief", "lead")


# Inventory: every cascade and SET NULL is decided, and matches the schema ----

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


async def _count(db, model, *where) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(*where))


async def _delete(w, who: str, path: str):
    return await aw.request(w, who, "DELETE", path)


def _assert_blocked(resp, *counts: str) -> None:
    assert resp.status_code == 409, resp.text
    for count in counts:
        assert count in resp.json()["detail"]


def _scoped_rows(scope_type: str, scope_id: uuid.UUID) -> list:
    """One row of every polymorphic table that points at an initiatief/lead."""
    key = aw.mm_id()
    return [
        MattermostChannelLink(
            channel_id=aw.mm_id(), channel_name="kanaal", channel_display_name="Kanaal",
            scope_type=scope_type, scope_id=scope_id,
        ),
        MattermostPostLink(
            post_id=key, channel_id=aw.mm_id(), scope_type=scope_type, scope_id=scope_id
        ),
        ParlementairAbonnement(
            scope_type=scope_type, scope_id=scope_id, term="Regelrecht",
            term_genormaliseerd=f"regelrecht-{key}",
        ),
        GitHubLink(
            scope_type=scope_type, scope_id=scope_id, link_type="pull_request",
            url=f"https://github.com/o/r/pull/{key}", owner="o", repo="r",
        ),
        Signaalcontext(scope_type=scope_type, scope_id=scope_id, tekst="context"),
    ]  # fmt: skip


_SCOPED = (MattermostChannelLink, MattermostPostLink, ParlementairAbonnement,
           GitHubLink, Signaalcontext)  # fmt: skip


async def _scoped_left(db, scope_type: str, scope_id: uuid.UUID) -> dict[str, int]:
    """What still points at a deleted record: scoped rows and grants."""
    left = {}
    for model in (*_SCOPED, ResourcePermission):
        rp_ = model is ResourcePermission
        typ = model.resource_type if rp_ else model.scope_type
        rid = model.resource_id if rp_ else model.scope_id
        if n := await _count(db, model, typ == scope_type, rid == scope_id):
            left[model.__tablename__] = n
    return left


# Node: tasks, opdrachten and links elsewhere block ---------------------------


@pytest.mark.parametrize(("who", "expected"), [("manager", 409), ("super_admin", 204)])
async def test_node_delete_keeps_work_of_other_units(world, who, expected):
    """The directie manager holds node:delete, tenant-wide for a node without
    eenheid, but no rights in ``elders``: its task and opdracht block."""
    t = aw.task(world, "Taak elders op vrije node", "node_free", "elders")
    o = aw.opdracht(
        world, "Opdracht elders", "elders", instrument_id=world.res["node_free"]
    )
    await aw.add(world, t, o)
    t_id, o_id = t.id, o.id
    resp = await _delete(world, who, "/api/nodes/{node_free}")
    if expected == 409:
        _assert_blocked(resp, "1 taak", "1 opdracht")
    assert resp.status_code == expected, resp.text
    world.db.expire_all()
    kept = int(expected == 409)
    assert await _count(world.db, Task, Task.id == t_id) == kept
    assert await _count(world.db, Opdracht, Opdracht.id == o_id) == kept


async def test_node_delete_takes_own_work_and_removes_what_points_at_it(world):
    """Tasks the caller may delete go with the node; grants, assessments and
    mentions are removed, not orphaned.  An item's suggestions would fall to
    anyone holding parlementair:review: they go too, the item stays."""
    db, node_id = world.db, world.res["node_directie"]
    item = await aw.make_item(world, "node_directie")
    await aw.add(
        world,
        StakeholderAssessment(person_id=world.person["viewer"].id,
                              scope_type="corpus_node", scope_id=node_id),
        Mention(source_type="task", source_id=world.res["task_team"],
                mention_type="node", target_id=node_id),
        SuggestedEdge(parlementair_item_id=item.id, confidence=0.9,
                      target_node_id=world.res["node_elders"],
                      edge_type_id=world.res["edge_type"]),
    )  # fmt: skip
    item_id = item.id
    resp = await _delete(world, "manager", "/api/nodes/{node_directie}")
    assert resp.status_code == 204, resp.text
    db.expire_all()
    sa, se, pi = StakeholderAssessment, SuggestedEdge, ParlementairItem
    assert await _count(db, Task, Task.id == world.res["task_team"]) == 0
    assert await _scoped_left(db, "corpus_node", node_id) == {}
    assert await _count(db, sa, sa.scope_id == node_id) == 0
    assert await _count(db, Mention, Mention.target_id == node_id) == 0
    assert await _count(db, se, se.parlementair_item_id == item_id) == 0
    assert await db.scalar(select(pi.corpus_node_id).where(pi.id == item_id)) is None


async def test_node_delete_refuses_links_of_records_the_caller_may_not_change(
    world,
):
    """A lead's or opdracht's link to the node is theirs to lose."""
    other = await aw.add(world, Initiatief(id=uuid.uuid4(), naam=f"Ander {aw.mm_id()}"))
    lead = Lead(title="Lead elders", stage="verkennen", initiatief_id=other.id)
    o = aw.opdracht(world, "Opdracht elders", "elders")
    await aw.add(world, lead, o)
    node = world.res["node_directie"]
    await aw.add(world, LeadNode(lead_id=lead.id, node_id=node),
              OpdrachtNode(opdracht_id=o.id, node_id=node))  # fmt: skip
    resp = await _delete(world, "manager", "/api/nodes/{node_directie}")
    _assert_blocked(resp, "1 lead", "1 opdracht")
    assert await _count(world.db, LeadNode, LeadNode.lead_id == lead.id) == 1


# Initiatief: its leads and everything scoped to it go with it ----------------


async def test_initiatief_delete_leaves_nothing_behind(iw):
    db, init_id, lead_id = iw.db, iw.res["initiatief"], iw.res["lead"]
    viewer = iw.person["viewer"]
    await aw.add(
        iw, *_scoped_rows("initiatief", init_id), *_scoped_rows("lead", lead_id),
        StakeholderAssessment(person_id=viewer.id, scope_type="initiatief",
                              scope_id=init_id),
        InitiatiefUpdatePost(initiatief_id=init_id, titel="Update", body="x"),
        LeadActivity(lead_id=lead_id, content="Gesprek", activity_type="note"),
        aw.rp("lead", lead_id, "contactpersoon", person=viewer),
    )  # fmt: skip
    # It still needs initiatief:delete.
    refused = await _delete(iw, "viewer", "/api/initiatieven/{initiatief}")
    assert refused.status_code in (403, 404)
    assert await db.get(Lead, lead_id) is not None

    resp = await _delete(iw, "afd_editor", "/api/initiatieven/{initiatief}")
    assert resp.status_code == 204, resp.text
    # A team viewer gains nothing from it.
    assert (
        await aw.request(iw, "viewer", "GET", "/api/leads/{lead}")
    ).status_code == 404
    listed = await aw.request(iw, "viewer", "GET", "/api/leads")
    assert str(lead_id) not in {i["id"] for i in listed.json()}
    db.expire_all()
    # The lead is gone, not left behind without initiatief; no alert keeps
    # going to a channel of a deleted initiatief or lead.
    assert await _count(db, Lead, Lead.id == lead_id) == 0
    assert await _count(db, LeadActivity, LeadActivity.lead_id == lead_id) == 0
    assert await _scoped_left(db, "initiatief", init_id) == {}
    assert await _scoped_left(db, "lead", lead_id) == {}
    columns = (LeadColumn.initiatief_id, InitiatiefUpdatePost.initiatief_id,
               StakeholderAssessment.scope_id)  # fmt: skip
    for column in columns:
        assert await _count(db, column.class_, column == init_id) == 0


# Task, opdracht and lead -----------------------------------------------------


@pytest.mark.parametrize(
    ("node", "eenheid", "who", "expected"),
    [
        ("node_elders", "elders", "team_editor", 409),  # not theirs to delete
        ("node_elders", "elders", "super_admin", 204),
        ("node_directie", "team", "team_editor", 204),  # own subtask goes along
    ],
)
async def test_task_delete_and_its_subtasks(world, node, eenheid, who, expected):
    sub = aw.task(world, "Subtaak", node, eenheid, parent_id=world.res["task_team"])
    sub_id = (await aw.add(world, sub)).id
    resp = await _delete(world, who, "/api/tasks/{task_team}")
    if expected == 409:
        _assert_blocked(resp, "1 taak")
    assert resp.status_code == expected, resp.text
    world.db.expire_all()
    assert await _count(world.db, Task, Task.id == sub_id) == int(expected == 409)


async def test_opdracht_delete_removes_grants_and_koppelingen(world):
    db, opdracht_id = world.db, world.res["opdracht_directie"]
    t = aw.task(world, "Taak", "node_directie", "directie", opdracht_id=opdracht_id)
    koppeling = OpdrachtNode(opdracht_id=opdracht_id, node_id=world.res["node_elders"])
    viewer = world.person["viewer"]
    await aw.add(
        world, t, koppeling, aw.rp("opdracht", opdracht_id, "betrokken", person=viewer)
    )
    task_id = t.id
    resp = await _delete(world, "manager", "/api/opdrachten/{opdracht_directie}")
    assert resp.status_code == 204, resp.text
    db.expire_all()
    assert await _count(db, OpdrachtNode, OpdrachtNode.opdracht_id == opdracht_id) == 0
    assert await _scoped_left(db, "opdracht", opdracht_id) == {}
    # The task lives on its node and eenheid: it stays, without the opdracht.
    assert await db.scalar(select(Task.opdracht_id).where(Task.id == task_id)) is None


@pytest.mark.parametrize("how", ["delete", "merge"])
async def test_lead_delete_and_merge_leave_nothing_scoped_to_it(iw, how):
    """Merging deletes the source: its channel links and abonnementen go too."""
    db, lead_id = iw.db, iw.res["lead"]
    target = Lead(title="Doel", stage="verkennen", initiatief_id=iw.res["initiatief"])
    await aw.add(
        iw, target, *_scoped_rows("lead", lead_id),
        LeadActivity(lead_id=lead_id, content="Gesprek", activity_type="note"),
        aw.rp("lead", lead_id, "contactpersoon", person=iw.person["viewer"]),
    )  # fmt: skip
    if how == "delete":
        resp = await _delete(iw, "afd_editor", "/api/leads/{lead}")
    else:
        body = {"source_id": str(lead_id), "target_id": str(target.id)}
        resp = await aw.request(iw, "afd_editor", "POST", "/api/leads/merge", body)
    assert resp.status_code == (204 if how == "delete" else 200), resp.text
    db.expire_all()
    assert await _count(db, Lead, Lead.id == lead_id) == 0
    assert await _scoped_left(db, "lead", lead_id) == {}
