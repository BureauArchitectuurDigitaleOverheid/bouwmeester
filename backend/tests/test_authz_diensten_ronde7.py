"""Background services keep what they produce where it belongs (round 7).

Uses ``world`` from ``tests/authz_world.py``.
"""

from sqlalchemy import select

from bouwmeester.core.authz import can
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.task import Task
from bouwmeester.services.opdracht_task_service import OpdrachtTaskService
from tests.authz_world import World, perm_ctx

# ---------------------------------------------------------------------------
# Opdracht worker tasks live where the opdracht lives
# ---------------------------------------------------------------------------


async def _opdracht_tasks(w: World, **placing) -> list[Task]:
    opdracht = Opdracht(
        type="opdracht",
        titel="Geheime opdracht",
        begrotingsjaar=2026,
        instrument_id=w.res["node_team"],
        verantwoordelijke_id=w.person["viewer"].id,
        **placing,
    )
    w.db.add(opdracht)
    await w.db.flush()
    await OpdrachtTaskService(w.db).on_opdracht_created(opdracht)
    return list(
        (await w.db.scalars(select(Task).where(Task.opdracht_id == opdracht.id))).all()
    )


async def test_opdracht_task_lives_in_the_opdracht_eenheid(world):
    """The instrument's readers and editors do not get the opdracht's task."""
    (task,) = await _opdracht_tasks(world, opdrachtgever_id=world.org["elders"].id)

    assert task.organisatie_eenheid_id == world.org["elders"].id
    assert task.title == "Opdracht formaliseren: Geheime opdracht"
    ctx = await perm_ctx(world, "team_editor")
    assert not await can(world.db, ctx, "task:read", "task", task.id)
    assert not await can(world.db, ctx, "task:update", "task", task.id)


async def test_opdracht_task_falls_back_to_the_opdrachtnemer(world):
    (task,) = await _opdracht_tasks(
        world, opdrachtnemer_eenheid_id=world.org["elders"].id
    )

    assert task.organisatie_eenheid_id == world.org["elders"].id


async def test_opdracht_task_without_eenheid_has_a_generic_title(world):
    (task,) = await _opdracht_tasks(world)

    assert task.organisatie_eenheid_id is None
    assert task.title == "Opdracht formaliseren"
