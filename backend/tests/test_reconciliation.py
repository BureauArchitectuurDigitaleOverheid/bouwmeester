"""Tests voor reconciliation merge/ignore endpoints."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.lead import Lead
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.pending_reconciliation import PendingReconciliation


@pytest.fixture
async def reconciliation_setup(db_session: AsyncSession):
    """Setup: handmatige + TOOI-rij + open reconciliation."""
    handmatig = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Test Org",
        type="zbo",
        bron="handmatig",
        afkorting="TST",
        website="https://test.example",
    )
    tooi = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Test Org",
        type="zbo",
        bron="tooi",
        tooi_uri="https://identifier.overheid.nl/tooi/id/test/x1",
    )
    db_session.add_all([handmatig, tooi])
    await db_session.flush()

    rec = PendingReconciliation(
        id=uuid.uuid4(),
        resource_type="organisatie_eenheid",
        handmatige_id=handmatig.id,
        kandidaat_id=tooi.id,
        kandidaat_bron="tooi",
        match_reden="naam_normalized",
        status="open",
    )
    db_session.add(rec)
    await db_session.flush()
    return {"handmatig": handmatig, "tooi": tooi, "rec": rec}


async def test_reconciliation_list_open(client, reconciliation_setup):
    resp = await client.get("/api/admin/reconciliation?status=open")
    assert resp.status_code == 200
    data = resp.json()
    assert any(r["id"] == str(reconciliation_setup["rec"].id) for r in data)


async def test_reconciliation_merge_verplaatst_lead_fk(
    client, db_session: AsyncSession, reconciliation_setup
):
    """Mergen verplaatst Lead.organisatie_eenheid_id van handmatig naar TOOI."""
    handmatig = reconciliation_setup["handmatig"]
    tooi = reconciliation_setup["tooi"]
    rec = reconciliation_setup["rec"]

    lead = Lead(
        id=uuid.uuid4(),
        title="Test lead",
        stage="verkennen",
        organisatie_eenheid_id=handmatig.id,
    )
    db_session.add(lead)
    await db_session.flush()

    resp = await client.post(f"/api/admin/reconciliation/{rec.id}/merge")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "merged"
    assert data["doelrij_id"] == str(tooi.id)

    # Verifieer Lead-FK is verplaatst
    await db_session.refresh(lead)
    assert lead.organisatie_eenheid_id == tooi.id

    # Handmatige rij is verwijderd
    nog_handmatig = (
        (
            await db_session.execute(
                select(OrganisatieEenheid).where(OrganisatieEenheid.id == handmatig.id)
            )
        )
        .scalars()
        .first()
    )
    assert nog_handmatig is None


async def test_reconciliation_merge_verplaatst_opdracht_fk(
    client, db_session: AsyncSession, reconciliation_setup, sample_person
):
    """Mergen verplaatst Opdracht.opdrachtnemer_eenheid_id naar TOOI."""
    from bouwmeester.models.corpus_node import CorpusNode

    handmatig = reconciliation_setup["handmatig"]
    tooi = reconciliation_setup["tooi"]
    rec = reconciliation_setup["rec"]

    instr = CorpusNode(
        id=uuid.uuid4(),
        title="Instr",
        node_type="instrument",
        status="actief",
    )
    db_session.add(instr)
    await db_session.flush()

    opdr = Opdracht(
        id=uuid.uuid4(),
        titel="Test opdracht",
        type="opdracht",
        status="actief",
        begrotingsjaar=2025,
        instrument_id=instr.id,
        opdrachtnemer_eenheid_id=handmatig.id,
        verantwoordelijke_id=sample_person.id,
    )
    db_session.add(opdr)
    await db_session.flush()

    resp = await client.post(f"/api/admin/reconciliation/{rec.id}/merge")
    assert resp.status_code == 200

    await db_session.refresh(opdr)
    assert opdr.opdrachtnemer_eenheid_id == tooi.id


async def test_reconciliation_merge_kopieert_ontbrekende_velden(
    client, db_session: AsyncSession, reconciliation_setup
):
    """Mergen kopieert afkorting/website van handmatig naar TOOI als TOOI ze mist."""
    tooi = reconciliation_setup["tooi"]
    rec = reconciliation_setup["rec"]

    # Tooi heeft geen afkorting of website
    assert tooi.afkorting is None
    assert tooi.website is None

    resp = await client.post(f"/api/admin/reconciliation/{rec.id}/merge")
    assert resp.status_code == 200

    await db_session.refresh(tooi)
    assert tooi.afkorting == "TST"
    assert tooi.website == "https://test.example"


async def test_reconciliation_ignore(
    client, db_session: AsyncSession, reconciliation_setup
):
    """Negeren laat beide rijen bestaan, status -> ignored."""
    rec = reconciliation_setup["rec"]
    resp = await client.post(f"/api/admin/reconciliation/{rec.id}/ignore")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"

    await db_session.refresh(rec)
    assert rec.status == "ignored"


async def test_reconciliation_merge_404_op_nonexistent(client):
    fake_id = uuid.uuid4()
    resp = await client.post(f"/api/admin/reconciliation/{fake_id}/merge")
    assert resp.status_code == 404


async def test_reconciliation_merge_404_op_reeds_gemerged(
    client, db_session: AsyncSession, reconciliation_setup
):
    rec = reconciliation_setup["rec"]
    rec.status = "merged"
    await db_session.flush()
    resp = await client.post(f"/api/admin/reconciliation/{rec.id}/merge")
    assert resp.status_code == 404


async def test_reconciliation_merge_verplaatst_children(
    client, db_session: AsyncSession, reconciliation_setup
):
    """Bron met sub-eenheden (parent_id RESTRICT) faalde voorheen op delete.

    Dit is het BZK-scenario in productie: handmatige BZK heeft DG's en
    directies hangen via parent_id. Zonder parent_id-rewrite gaf delete
    een ForeignKeyViolation -> 500.
    """
    handmatig = reconciliation_setup["handmatig"]
    tooi = reconciliation_setup["tooi"]
    rec = reconciliation_setup["rec"]

    child1 = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Sub DG 1",
        type="directoraat_generaal",
        bron="handmatig",
        parent_id=handmatig.id,
    )
    child2 = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Sub DG 2",
        type="directoraat_generaal",
        bron="handmatig",
        parent_id=handmatig.id,
    )
    db_session.add_all([child1, child2])
    await db_session.flush()

    resp = await client.post(f"/api/admin/reconciliation/{rec.id}/merge")
    assert resp.status_code == 200, resp.text

    await db_session.refresh(child1)
    await db_session.refresh(child2)
    assert child1.parent_id == tooi.id
    assert child2.parent_id == tooi.id

    nog_handmatig = (
        (
            await db_session.execute(
                select(OrganisatieEenheid).where(OrganisatieEenheid.id == handmatig.id)
            )
        )
        .scalars()
        .first()
    )
    assert nog_handmatig is None


async def test_reconciliation_merge_dedup_op_eenheid_module(
    client, db_session: AsyncSession, reconciliation_setup
):
    """Als bron en doel allebei dezelfde module-key hebben dedupliceren."""
    from bouwmeester.models.eenheid_module import EenheidModule

    handmatig = reconciliation_setup["handmatig"]
    tooi = reconciliation_setup["tooi"]
    rec = reconciliation_setup["rec"]

    # Beide rijen hebben dezelfde module_key — zou unique_constraint
    # schenden bij naïeve UPDATE.
    db_session.add_all(
        [
            EenheidModule(
                organisatie_eenheid_id=handmatig.id,
                module="leads",
                enabled=True,
            ),
            EenheidModule(
                organisatie_eenheid_id=tooi.id,
                module="leads",
                enabled=False,
            ),
            # En een module die alleen op handmatig zit -> moet wel mee.
            EenheidModule(
                organisatie_eenheid_id=handmatig.id,
                module="opdrachten",
                enabled=True,
            ),
        ]
    )
    await db_session.flush()

    resp = await client.post(f"/api/admin/reconciliation/{rec.id}/merge")
    assert resp.status_code == 200, resp.text

    rows = (
        (
            await db_session.execute(
                select(EenheidModule).where(
                    EenheidModule.organisatie_eenheid_id == tooi.id
                )
            )
        )
        .scalars()
        .all()
    )
    keys = {r.module for r in rows}
    assert keys == {"leads", "opdrachten"}
