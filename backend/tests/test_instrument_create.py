"""Tests for instrument-node creation with an explicit instrument_type,
and for the alphabetical ordering of the node list."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.instrument import Instrument


async def test_create_instrument_with_explicit_type(client, db_session: AsyncSession):
    """POST /api/nodes with instrument_type sets Instrument.type accordingly."""
    resp = await client.post(
        "/api/nodes",
        json={
            "title": "Subsidieregeling open source",
            "node_type": "instrument",
            "instrument_type": "subsidie",
        },
    )
    assert resp.status_code == 201
    node_id = resp.json()["id"]

    instrument = (
        await db_session.execute(select(Instrument).where(Instrument.id == node_id))
    ).scalar_one()
    assert instrument.type == "subsidie"


async def test_create_instrument_defaults_to_overig(client, db_session: AsyncSession):
    """Omitting instrument_type keeps the existing default of 'overig'
    (backwards compatible with all other create paths)."""
    resp = await client.post(
        "/api/nodes",
        json={"title": "Naamloos instrument", "node_type": "instrument"},
    )
    assert resp.status_code == 201
    node_id = resp.json()["id"]

    instrument = (
        await db_session.execute(select(Instrument).where(Instrument.id == node_id))
    ).scalar_one()
    assert instrument.type == "overig"


async def test_create_instrument_rejects_unknown_type(client):
    """An instrument_type outside the allowed set is a 422."""
    resp = await client.post(
        "/api/nodes",
        json={
            "title": "Fout instrument",
            "node_type": "instrument",
            "instrument_type": "geldboom",
        },
    )
    assert resp.status_code == 422


async def test_list_nodes_sorted_alphabetically(client):
    """GET /api/nodes returns nodes ordered alphabetically by title,
    so selection dropdowns are usable."""
    for title in ["Zebra-instrument", "Alfa-instrument", "Midden-instrument"]:
        resp = await client.post(
            "/api/nodes",
            json={"title": title, "node_type": "instrument"},
        )
        assert resp.status_code == 201

    resp = await client.get("/api/nodes", params={"node_type": "instrument"})
    assert resp.status_code == 200
    titles = [n["title"] for n in resp.json()]
    assert titles == sorted(titles)
