"""Only super_admin instructs an agent (product decision).

An agent acts on what it is handed with its own rights, not the sender's.
Assigning it a task or a lead, or @mentioning it, hands it work just like a
DM does, so every path answers to the same rule
(``services.agent_rules``).
"""

from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from bouwmeester.core.authority import (
    require_can_assign_role,
    require_can_change_resource_role,
    require_can_decide_placement_request,
    require_can_grant_resource_role,
    require_can_name_owner,
    require_can_place,
    require_can_set_manager,
)
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.lead import Lead
from bouwmeester.models.notification import Notification
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.role import Role
from bouwmeester.models.task import Task
from bouwmeester.services.chat_service import _execute_write_tool
from bouwmeester.services.mention_helper import sync_and_notify_mentions
from bouwmeester.services.notification_service import NotificationService
from bouwmeester.services.opdracht_task_service import OpdrachtTaskService
from tests.authz_world import make_item, perm_ctx
from tests.factories import client_as, make_person, place

EDITOR = "afd_editor"
ADMIN = "super_admin"
REFUSED = "Alleen systeembeheerders mogen een agent aansturen"


@pytest.fixture
async def agent(world):
    person = await make_person(world.db, "Agent")
    person.is_agent = True
    await place(world.db, person, world.org["afdeling"])  # reads what it gets
    await world.db.flush()
    return person


def _task_body(world, assignee):
    return {
        "title": "Doe iets",
        "node_id": str(world.res["node_afdeling"]),
        "organisatie_eenheid_id": str(world.org["afdeling"].id),
        "assignee_id": str(assignee.id),
    }


def _lead_body(world, assignee):
    return {
        "title": "Gemeente",
        "initiatief_id": str(world.res["initiatief"]),
        "assignee_id": str(assignee.id),
    }


@pytest.mark.parametrize(("who", "expected"), [(EDITOR, 403), (ADMIN, 201)])
async def test_rest_task_create_with_agent(world, agent, who, expected):
    async with client_as(world.db, world.person[who]) as c:
        resp = await c.post("/api/tasks", json=_task_body(world, agent))
    assert resp.status_code == expected, resp.text


@pytest.mark.parametrize(("who", "expected"), [(EDITOR, 403), (ADMIN, 200)])
async def test_rest_task_update_to_agent(world, agent, who, expected):
    task = Task(
        title="Taak",
        node_id=world.res["node_afdeling"],
        organisatie_eenheid_id=world.org["afdeling"].id,
        status="open",
    )
    world.db.add(task)
    await world.db.flush()
    async with client_as(world.db, world.person[who]) as c:
        resp = await c.put(f"/api/tasks/{task.id}", json={"assignee_id": str(agent.id)})
    assert resp.status_code == expected, resp.text


async def test_rest_task_update_keeping_the_agent_is_fine(world, agent):
    """Someone else set the agent; editing the task does not instruct it."""
    task = Task(
        title="Taak",
        node_id=world.res["node_afdeling"],
        organisatie_eenheid_id=world.org["afdeling"].id,
        status="open",
        assignee_id=agent.id,
    )
    world.db.add(task)
    await world.db.flush()
    async with client_as(world.db, world.person[EDITOR]) as c:
        resp = await c.put(
            f"/api/tasks/{task.id}",
            json={"title": "Nieuwe titel", "assignee_id": str(agent.id)},
        )
    assert resp.status_code == 200, resp.text


@pytest.mark.parametrize(("who", "expected"), [(EDITOR, 403), (ADMIN, 201)])
async def test_rest_lead_create_with_agent(world, agent, who, expected):
    async with client_as(world.db, world.person[who]) as c:
        resp = await c.post("/api/leads", json=_lead_body(world, agent))
    assert resp.status_code == expected, resp.text


@pytest.mark.parametrize(("who", "expected"), [(EDITOR, 403), (ADMIN, 200)])
async def test_rest_lead_update_to_agent(world, agent, who, expected):
    async with client_as(world.db, world.person[who]) as c:
        resp = await c.put(
            f"/api/leads/{world.res['lead']}", json={"assignee_id": str(agent.id)}
        )
    assert resp.status_code == expected, resp.text


@pytest.mark.parametrize("who", [EDITOR, ADMIN])
async def test_chat_create_task_with_agent(world, agent, who):
    args = {
        "title": "Doe iets",
        "node_id": str(world.res["node_afdeling"]),
        "organisatie_eenheid_id": str(world.org["afdeling"].id),
        "assignee_id": str(agent.id),
    }
    result = await _execute_write_tool(
        "create_task", args, world.db, person_id=world.person[who].id
    )
    assert result["success"] is (who == ADMIN), result
    if who == EDITOR:
        assert result["summary"] == REFUSED


@pytest.mark.parametrize("who", [EDITOR, ADMIN])
async def test_chat_create_lead_with_agent(world, agent, who):
    args = {
        "title": "Gemeente",
        "initiatief_id": str(world.res["initiatief"]),
        "assignee_id": str(agent.id),
    }
    result = await _execute_write_tool(
        "create_lead", args, world.db, person_id=world.person[who].id
    )
    assert result["success"] is (who == ADMIN), result


@pytest.mark.parametrize("who", [EDITOR, ADMIN])
async def test_chat_update_lead_to_agent(world, agent, who):
    args = {"lead_id": str(world.res["lead"]), "assignee_id": str(agent.id)}
    result = await _execute_write_tool(
        "update_lead", args, world.db, person_id=world.person[who].id
    )
    assert result["success"] is (who == ADMIN), result
    lead = await world.db.get(Lead, world.res["lead"])
    await world.db.refresh(lead)
    assert (lead.assignee_id == agent.id) is (who == ADMIN)


@pytest.mark.parametrize("who", [EDITOR, ADMIN])
async def test_mention_of_agent_notifies_only_from_super_admin(world, agent, who):
    task = Task(
        title="Taak met mention",
        node_id=world.res["node_afdeling"],
        organisatie_eenheid_id=world.org["afdeling"].id,
        status="open",
    )
    world.db.add(task)
    await world.db.flush()

    await sync_and_notify_mentions(
        world.db,
        "task",
        task.id,
        f"Kun jij dit oppakken [@Agent](user:{agent.id})",
        task.title,
        sender_id=world.person[who].id,
        source_task_id=task.id,
    )

    notes = await world.db.execute(
        select(Notification).where(
            Notification.person_id == agent.id, Notification.type == "mention"
        )
    )
    assert (notes.scalars().first() is not None) is (who == ADMIN)


@pytest.mark.parametrize(("who", "expected"), [(EDITOR, 403), (ADMIN, 200)])
async def test_opdracht_verantwoordelijke_agent(world, agent, who, expected):
    """The verantwoordelijke gets the opdracht's follow-up tasks: an instruction."""
    async with client_as(world.db, world.person[who]) as c:
        resp = await c.put(
            f"/api/opdrachten/{world.res['opdracht_free']}",
            json={"verantwoordelijke_id": str(agent.id)},
        )
    assert resp.status_code == expected, resp.text


# Work and notifications the system generates -------------------------------


async def _opdracht_with_agent(world, verantwoordelijke) -> Opdracht:
    instrument = CorpusNode(
        title="Instrument",
        node_type="instrument",
        status="actief",
        organisatie_eenheid_id=world.org["afdeling"].id,
    )
    world.db.add(instrument)
    await world.db.flush()
    opdracht = Opdracht(
        type="opdracht",
        titel="Opdracht met agent",
        begrotingsjaar=2026,
        status="actief",
        instrument_id=instrument.id,
        verantwoordelijke_id=verantwoordelijke.id,
        einddatum=date.today() + timedelta(days=10),
    )
    world.db.add(opdracht)
    await world.db.flush()
    return opdracht


async def _tasks_of(world, opdracht) -> list[Task]:
    return list(
        (
            await world.db.scalars(select(Task).where(Task.opdracht_id == opdracht.id))
        ).all()
    )


async def test_generated_opdracht_tasks_are_not_assigned_to_an_agent(world, agent):
    """Whoever may edit the opdracht would otherwise instruct its agent."""
    opdracht = await _opdracht_with_agent(world, agent)
    service = OpdrachtTaskService(world.db)
    await service.on_opdracht_created(opdracht)
    opdracht.status = "afgerond"
    await service.on_status_changed(opdracht, "actief")
    opdracht.status = "actief"
    await service.check_deadlines()

    tasks = await _tasks_of(world, opdracht)
    assert {t.work_type for t in tasks} == {
        "Formalisatie",
        "Verantwoording",
        "Deadline",
    }
    assert all(t.assignee_id is None for t in tasks)


async def test_generated_opdracht_tasks_still_go_to_a_person(world):
    person = world.person["afd_editor"]
    opdracht = await _opdracht_with_agent(world, person)
    await OpdrachtTaskService(world.db).on_opdracht_created(opdracht)
    assert [t.assignee_id for t in await _tasks_of(world, opdracht)] == [person.id]


async def test_opdracht_status_route_leaves_agent_task_unassigned(world, agent):
    opdracht = await _opdracht_with_agent(world, agent)
    async with client_as(world.db, world.person[EDITOR]) as c:
        resp = await c.put(
            f"/api/opdrachten/{opdracht.id}", json={"status": "afgerond"}
        )
    assert resp.status_code == 200, resp.text
    tasks = await _tasks_of(world, opdracht)
    assert tasks and all(t.assignee_id is None for t in tasks)


async def _agent_notifications(world, agent, type_: str) -> list[Notification]:
    return list(
        (
            await world.db.scalars(
                select(Notification).where(
                    Notification.person_id == agent.id, Notification.type == type_
                )
            )
        ).all()
    )


@pytest.mark.parametrize("who", [EDITOR, ADMIN, None])
async def test_agent_stakeholder_notified_only_by_super_admin(world, agent, who):
    """An informational notification hands the agent work too."""
    opdracht = await _opdracht_with_agent(world, world.person["afd_editor"])
    world.db.add(
        ResourcePermission(
            person_id=agent.id,
            resource_type="corpus_node",
            resource_id=opdracht.instrument_id,
            rol="betrokken",
        )
    )
    await world.db.flush()
    actor_id = world.person[who].id if who else None
    await NotificationService(world.db).notify_opdracht_assigned(
        opdracht, actor_id=actor_id
    )
    notes = await _agent_notifications(world, agent, "opdracht_created")
    assert bool(notes) is (who == ADMIN)


@pytest.mark.parametrize("who", [EDITOR, ADMIN])
async def test_task_assigned_notification_reaches_agent_from_super_admin(
    world, agent, who
):
    task = Task(
        title="Taak",
        node_id=world.res["node_afdeling"],
        organisatie_eenheid_id=world.org["afdeling"].id,
        status="open",
    )
    world.db.add(task)
    await world.db.flush()
    await NotificationService(world.db).notify_task_assigned(
        task, agent, actor_id=world.person[who].id
    )
    notes = await _agent_notifications(world, agent, "task_assigned")
    assert bool(notes) is (who == ADMIN)


# Mentions in nodes and eenheden carry their sender --------------------------


@pytest.mark.parametrize("who", [EDITOR, ADMIN])
async def test_node_mention_of_agent_only_from_super_admin(world, agent, who):
    async with client_as(world.db, world.person[who]) as c:
        resp = await c.put(
            f"/api/nodes/{world.res['node_afdeling']}",
            json={"description": f"Oppakken [@Agent](user:{agent.id})"},
        )
    assert resp.status_code == 200, resp.text
    assert bool(await _agent_notifications(world, agent, "mention")) is (who == ADMIN)


@pytest.mark.parametrize("who", ["manager", ADMIN])
async def test_eenheid_mention_of_agent_only_from_super_admin(world, agent, who):
    async with client_as(world.db, world.person[who]) as c:
        resp = await c.put(
            f"/api/organisatie/{world.org['afdeling'].id}",
            json={"beschrijving": f"Contact [@Agent](user:{agent.id})"},
        )
    assert resp.status_code == 200, resp.text
    assert bool(await _agent_notifications(world, agent, "mention")) is (who == ADMIN)


# Roles, grants and placements are power ------------------------------------

MANAGER = "manager"  # unit_manager of the directie: may place, assign, grant


async def _guard_refuses(world, who, guard) -> bool:
    ctx = await perm_ctx(world, who)
    try:
        await guard(ctx)
    except HTTPException as exc:
        assert exc.status_code == 403
        return exc.detail == REFUSED
    return False


@pytest.mark.parametrize("who", [MANAGER, ADMIN])
async def test_placing_an_agent(world, agent, who):
    refused = await _guard_refuses(
        world,
        who,
        lambda ctx: require_can_place(world.db, ctx, agent, world.org["directie"]),
    )
    assert refused is (who == MANAGER)


@pytest.mark.parametrize("who", [MANAGER, ADMIN])
async def test_approving_an_agents_placement_request(world, agent, who):
    refused = await _guard_refuses(
        world,
        who,
        lambda ctx: require_can_decide_placement_request(
            world.db, ctx, requester_id=agent.id, eenheid_id=world.org["team"].id
        ),
    )
    assert refused is (who == MANAGER)


@pytest.mark.parametrize("who", [MANAGER, ADMIN])
async def test_assigning_an_agent_a_role(world, agent, who):
    role = await world.db.get(Role, "editor")
    refused = await _guard_refuses(
        world,
        who,
        lambda ctx: require_can_assign_role(
            world.db,
            ctx,
            role=role,
            eenheid_id=world.org["team"].id,
            target_person_id=agent.id,
        ),
    )
    assert refused is (who == MANAGER)


@pytest.mark.parametrize("who", [MANAGER, ADMIN])
async def test_naming_an_agent_manager(world, agent, who):
    refused = await _guard_refuses(
        world,
        who,
        lambda ctx: require_can_set_manager(
            world.db, ctx, eenheid_id=world.org["team"].id, new_manager_id=agent.id
        ),
    )
    assert refused is (who == MANAGER)


@pytest.mark.parametrize("who", [MANAGER, ADMIN])
async def test_granting_an_agent_a_resource_role(world, agent, who):
    refused = await _guard_refuses(
        world,
        who,
        lambda ctx: require_can_grant_resource_role(
            world.db,
            ctx,
            resource_type="corpus_node",
            resource_id=world.res["node_directie"],
            rol="betrokken",
            target_person_id=agent.id,
        ),
    )
    assert refused is (who == MANAGER)


async def _agent_grant(world, agent) -> ResourcePermission:
    grant = ResourcePermission(
        person_id=agent.id,
        resource_type="corpus_node",
        resource_id=world.res["node_directie"],
        rol="betrokken",
    )
    world.db.add(grant)
    await world.db.flush()
    return grant


@pytest.mark.parametrize("who", [MANAGER, ADMIN])
async def test_raising_an_agents_resource_role(world, agent, who):
    grant = await _agent_grant(world, agent)
    refused = await _guard_refuses(
        world,
        who,
        lambda ctx: require_can_change_resource_role(
            world.db, ctx, grant, new_rol="eigenaar"
        ),
    )
    assert refused is (who == MANAGER)


async def test_removing_an_agents_resource_role_is_not_empowering(world, agent):
    grant = await _agent_grant(world, agent)
    refused = await _guard_refuses(
        world,
        MANAGER,
        lambda ctx: require_can_change_resource_role(
            world.db, ctx, grant, new_rol=None
        ),
    )
    assert refused is False


@pytest.mark.parametrize("who", [MANAGER, ADMIN])
async def test_naming_an_agent_first_owner_of_a_parlementair_item(world, agent, who):
    item = await make_item(world, "node_directie")
    refused = await _guard_refuses(
        world,
        who,
        lambda ctx: require_can_name_owner(
            world.db, ctx, item.corpus_node_id, agent.id
        ),
    )
    assert refused is (who == MANAGER)
