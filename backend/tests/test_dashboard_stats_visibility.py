"""The dashboard counts only the corpus nodes the caller sees."""

from bouwmeester.core.authz import org_visibility
from bouwmeester.repositories.corpus_node import CorpusNodeRepository
from tests.authz_world import make_node, perm_ctx
from tests.factories import client_as


async def _count(world, who: str) -> int:
    async with client_as(world.db, world.person[who]) as c:
        resp = await c.get("/api/notifications/dashboard-stats")
    assert resp.status_code == 200, resp.text
    return resp.json()["corpus_node_count"]


async def test_hidden_node_is_not_counted(world):
    before = await _count(world, "viewer")
    await make_node(world.db, "Verborgen dossier", world.org["elders"])

    assert await _count(world, "viewer") == before
    ctx = await org_visibility(world.db, await perm_ctx(world, "viewer"))
    assert before == await CorpusNodeRepository(world.db).count(org_ctx=ctx)


async def test_super_admin_counts_every_node(world):
    before = await _count(world, "super_admin")
    await make_node(world.db, "Verborgen dossier", world.org["elders"])

    assert await _count(world, "super_admin") == before + 1
