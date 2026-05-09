"""Tests for opdrachten and financial features.

Externe organisaties zitten sinds de TOOI-migratie in OrganisatieEenheid.
De voormalige ExterneOrganisatie-tabel + bijbehorende /api/externe-organisaties
routes zijn verwijderd; tests die op die endpoints leunden zijn weg.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.repositories.opdracht import OpdrachtRepository
from bouwmeester.services.opdracht_task_service import OpdrachtTaskService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def instrument_node(db_session: AsyncSession):
    node = CorpusNode(
        id=uuid.uuid4(),
        title="Test instrument",
        node_type="instrument",
        status="actief",
    )
    db_session.add(node)
    await db_session.flush()
    return node


@pytest.fixture
async def extern_org_eenheid(db_session: AsyncSession):
    """Externe organisatie als OrganisatieEenheid (was: ExterneOrganisatie)."""
    org = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam=f"Test Org {uuid.uuid4().hex[:6]}",
        type="uitvoeringsorganisatie",
        bron="handmatig",
    )
    db_session.add(org)
    await db_session.flush()
    return org


@pytest.fixture
async def sample_opdracht(
    db_session: AsyncSession, instrument_node, extern_org_eenheid, sample_person
):
    opdracht = Opdracht(
        id=uuid.uuid4(),
        titel="Test opdracht",
        type="opdracht",
        status="actief",
        begrotingsjaar=2025,
        instrument_id=instrument_node.id,
        opdrachtnemer_eenheid_id=extern_org_eenheid.id,
        verantwoordelijke_id=sample_person.id,
        budget=Decimal("100000"),
        gerealiseerd=Decimal("50000"),
    )
    db_session.add(opdracht)
    await db_session.flush()
    return opdracht


# ---------------------------------------------------------------------------
# Opdrachten API tests
# ---------------------------------------------------------------------------


async def test_list_opdrachten(client, sample_opdracht):
    resp = await client.get("/api/opdrachten")
    assert resp.status_code == 200
    data = resp.json()
    assert any(o["id"] == str(sample_opdracht.id) for o in data)


async def test_get_opdracht(client, sample_opdracht):
    resp = await client.get(f"/api/opdrachten/{sample_opdracht.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["titel"] == "Test opdracht"
    assert data["status"] == "actief"


async def test_get_opdracht_not_found(client):
    resp = await client.get(f"/api/opdrachten/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_create_opdracht(
    client, instrument_node, extern_org_eenheid, sample_person
):
    resp = await client.post(
        "/api/opdrachten",
        json={
            "titel": "Nieuwe opdracht",
            "type": "opdracht",
            "status": "concept",
            "begrotingsjaar": 2025,
            "instrument_id": str(instrument_node.id),
            "opdrachtnemer_eenheid_id": str(extern_org_eenheid.id),
            "verantwoordelijke_id": str(sample_person.id),
            "budget": 50000,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["titel"] == "Nieuwe opdracht"
    assert data["begrotingsjaar"] == 2025


async def test_update_opdracht(client, sample_opdracht):
    resp = await client.put(
        f"/api/opdrachten/{sample_opdracht.id}",
        json={"titel": "Updated opdracht"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["titel"] == "Updated opdracht"
    assert "node_koppelingen" in data


async def test_delete_opdracht(client, sample_opdracht):
    resp = await client.delete(f"/api/opdrachten/{sample_opdracht.id}")
    assert resp.status_code == 204
    resp2 = await client.get(f"/api/opdrachten/{sample_opdracht.id}")
    assert resp2.status_code == 404


# ---------------------------------------------------------------------------
# Summary filters
# ---------------------------------------------------------------------------


async def test_summary_without_filters(client, sample_opdracht):
    resp = await client.get("/api/opdrachten/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    assert "totaal_budget" in data


async def test_summary_respects_instrument_filter(
    client, db_session, sample_opdracht, instrument_node
):
    """Summary should filter by instrument_id when provided."""
    other_node = CorpusNode(
        id=uuid.uuid4(),
        title="Other instrument",
        node_type="instrument",
        status="actief",
    )
    db_session.add(other_node)
    await db_session.flush()

    resp = await client.get(
        "/api/opdrachten/summary",
        params={"instrument_id": str(other_node.id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0


async def test_summary_respects_verantwoordelijke_filter(
    client, sample_opdracht, sample_person, create_person
):
    """Summary should filter by verantwoordelijke_id when provided."""
    other_person = await create_person(naam="Other Person", prefix="other")
    resp = await client.get(
        "/api/opdrachten/summary",
        params={"verantwoordelijke_id": str(other_person.id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0


# ---------------------------------------------------------------------------
# check_deadlines
# ---------------------------------------------------------------------------


async def test_check_deadlines_ignores_past_due(
    db_session, instrument_node, extern_org_eenheid, sample_person
):
    """Opdrachten with einddatum in the past should NOT get deadline tasks."""
    opdracht = Opdracht(
        id=uuid.uuid4(),
        titel="Old opdracht",
        type="opdracht",
        status="actief",
        begrotingsjaar=2024,
        instrument_id=instrument_node.id,
        opdrachtnemer_eenheid_id=extern_org_eenheid.id,
        verantwoordelijke_id=sample_person.id,
        einddatum=date.today() - timedelta(days=60),
    )
    db_session.add(opdracht)
    await db_session.flush()

    service = OpdrachtTaskService(db_session)
    count = await service.check_deadlines()
    assert count == 0


async def test_check_deadlines_picks_up_upcoming(
    db_session, instrument_node, extern_org_eenheid, sample_person
):
    """Opdrachten due within 30 days should get deadline tasks."""
    opdracht = Opdracht(
        id=uuid.uuid4(),
        titel="Upcoming opdracht",
        type="opdracht",
        status="actief",
        begrotingsjaar=2025,
        instrument_id=instrument_node.id,
        opdrachtnemer_eenheid_id=extern_org_eenheid.id,
        verantwoordelijke_id=sample_person.id,
        einddatum=date.today() + timedelta(days=15),
    )
    db_session.add(opdracht)
    await db_session.flush()

    service = OpdrachtTaskService(db_session)
    count = await service.check_deadlines()
    assert count == 1


async def test_check_deadlines_skips_far_future(
    db_session, instrument_node, extern_org_eenheid, sample_person
):
    """Opdrachten due more than 30 days out should NOT get deadline tasks."""
    opdracht = Opdracht(
        id=uuid.uuid4(),
        titel="Far future opdracht",
        type="opdracht",
        status="actief",
        begrotingsjaar=2025,
        instrument_id=instrument_node.id,
        opdrachtnemer_eenheid_id=extern_org_eenheid.id,
        verantwoordelijke_id=sample_person.id,
        einddatum=date.today() + timedelta(days=60),
    )
    db_session.add(opdracht)
    await db_session.flush()

    service = OpdrachtTaskService(db_session)
    count = await service.check_deadlines()
    assert count == 0


# ---------------------------------------------------------------------------
# OpdrachtRepository.update() eager loading
# ---------------------------------------------------------------------------


async def test_opdracht_update_returns_node_koppelingen(db_session, sample_opdracht):
    """update() returns opdracht with node_koppelingen (no MissingGreenlet)."""
    from bouwmeester.schema.opdracht import OpdrachtResponse, OpdrachtUpdate

    repo = OpdrachtRepository(db_session)
    updated = await repo.update(
        sample_opdracht.id,
        OpdrachtUpdate(titel="Updated titel"),
    )
    assert updated is not None
    # This would raise MissingGreenlet if node_koppelingen isn't eagerly loaded
    response = OpdrachtResponse.model_validate(updated)
    assert response.titel == "Updated titel"
    assert isinstance(response.node_koppelingen, list)
