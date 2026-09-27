"""Only super_admin instructs an agent (product decision).

An agent acts on what it is handed with its own rights, not the sender's.
Assigning it a task or a lead, or @mentioning it, hands it work just like a
DM does, so every path answers to the same rule
(``services.agent_rules``).
"""

import pytest
from sqlalchemy import select

from bouwmeester.models.lead import Lead
from bouwmeester.models.notification import Notification
from bouwmeester.models.task import Task
from bouwmeester.services.chat_service import _execute_write_tool
from bouwmeester.services.mention_helper import sync_and_notify_mentions
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
