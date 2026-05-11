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


async def test_reconciliation_merge_behoudt_historische_plaatsingen(
    client, db_session: AsyncSession, reconciliation_setup, sample_person
):
    """Regressie: historische plaatsingen op source moeten BLIJVEN bestaan,
    niet weggegooid worden door dedup. De partial-unique constraint op
    person_organisatie_eenheid is WHERE eind_datum IS NULL, dus historische
    rijen (eind_datum gevuld) botsen nooit en moeten gewoon mee."""
    from datetime import date

    from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid

    handmatig = reconciliation_setup["handmatig"]
    tooi = reconciliation_setup["tooi"]
    rec = reconciliation_setup["rec"]

    # 1) Historische plaatsing op source (eind_datum gevuld)
    historisch = PersonOrganisatieEenheid(
        id=uuid.uuid4(),
        person_id=sample_person.id,
        organisatie_eenheid_id=handmatig.id,
        start_datum=date(2020, 1, 1),
        eind_datum=date(2022, 1, 1),
    )
    # 2) Actieve plaatsing op source
    actief_source = PersonOrganisatieEenheid(
        id=uuid.uuid4(),
        person_id=sample_person.id,
        organisatie_eenheid_id=handmatig.id,
        start_datum=date(2024, 1, 1),
    )
    # 3) Actieve plaatsing op target — partial-unique conflict aanstaande
    actief_target = PersonOrganisatieEenheid(
        id=uuid.uuid4(),
        person_id=sample_person.id,
        organisatie_eenheid_id=tooi.id,
        start_datum=date(2023, 1, 1),
    )
    db_session.add_all([historisch, actief_source, actief_target])
    await db_session.flush()

    resp = await client.post(f"/api/admin/reconciliation/{rec.id}/merge")
    assert resp.status_code == 200, resp.text

    # Verifieer via raw SQL — de session cached oude IDs op de in-memory
    # objecten omdat de helper raw UPDATEs gebruikt, niet ORM-instances.
    from sqlalchemy import text

    rows = (
        await db_session.execute(
            text(
                "SELECT id, organisatie_eenheid_id, start_datum, eind_datum "
                "FROM person_organisatie_eenheid "
                "WHERE person_id = :p ORDER BY start_datum"
            ),
            {"p": sample_person.id},
        )
    ).all()
    assert len(rows) == 3, f"Verwacht 3 plaatsingen, kreeg {len(rows)} — data-verlies!"
    by_id = {r.id: r for r in rows}
    assert by_id[historisch.id].organisatie_eenheid_id == tooi.id
    assert by_id[historisch.id].eind_datum == date(2022, 1, 1)
    assert by_id[actief_source.id].organisatie_eenheid_id == tooi.id
    # Source's actieve plaatsing is afgesloten i.p.v. weggegooid
    assert by_id[actief_source.id].eind_datum is not None
    assert by_id[actief_target.id].organisatie_eenheid_id == tooi.id
    assert by_id[actief_target.id].eind_datum is None


async def test_reconciliation_merge_behoudt_verschillende_rollen(
    client, db_session: AsyncSession, reconciliation_setup
):
    """Regressie B2: resource_permission unique is (person, OE, type, id, rol).
    Scenario: target en source zijn beide subjects van permissions op een
    derde resource X — met verschillende rollen. Alleen identieke rollen
    mogen dedupen, verschillende rollen moeten blijven."""
    from sqlalchemy import text

    from bouwmeester.models.corpus_node import CorpusNode
    from bouwmeester.models.resource_permission import ResourcePermission

    handmatig = reconciliation_setup["handmatig"]
    tooi = reconciliation_setup["tooi"]
    rec = reconciliation_setup["rec"]

    # Twee derden — een corpus_node en de eenheden zelf zijn niet relevant.
    # We zetten permissions met person_id=None (eenheid-scoped) op
    # resource_type='corpus_node'.
    node = CorpusNode(
        id=uuid.uuid4(), title="Test node", node_type="dossier", status="actief"
    )
    db_session.add(node)
    await db_session.flush()

    # Source als subject: 'eigenaar' op de node
    perm_a = ResourcePermission(
        id=uuid.uuid4(),
        person_id=None,
        organisatie_eenheid_id=handmatig.id,
        resource_type="corpus_node",
        resource_id=node.id,
        rol="eigenaar",
    )
    # Target als subject: 'adviseur' op dezelfde node
    perm_b = ResourcePermission(
        id=uuid.uuid4(),
        person_id=None,
        organisatie_eenheid_id=tooi.id,
        resource_type="corpus_node",
        resource_id=node.id,
        rol="adviseur",
    )
    db_session.add_all([perm_a, perm_b])
    await db_session.flush()

    resp = await client.post(f"/api/admin/reconciliation/{rec.id}/merge")
    assert resp.status_code == 200, resp.text

    rows = (
        await db_session.execute(
            text(
                "SELECT rol FROM resource_permission "
                "WHERE organisatie_eenheid_id = :oe "
                "AND resource_id = :n"
            ),
            {"oe": tooi.id, "n": node.id},
        )
    ).all()
    rollen = {r.rol for r in rows}
    assert rollen == {"eigenaar", "adviseur"}, (
        f"Verschillende rollen verloren gegaan! rollen={rollen}"
    )


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


async def test_reconciliation_merge_geen_self_loop_in_parent(
    client, db_session: AsyncSession, reconciliation_setup
):
    """Regressie C5: source hangt al onder target. Na merge zou een naïeve
    UPDATE een self-loop (eenheid=target, parent=target) creëren in
    organisatie_eenheid_parent en organisatie_eenheid.parent_id.
    """
    from datetime import date

    from sqlalchemy import text

    handmatig = reconciliation_setup["handmatig"]
    tooi = reconciliation_setup["tooi"]
    rec = reconciliation_setup["rec"]

    # Source hangt onder target via direct parent_id
    handmatig.parent_id = tooi.id
    # Plus temporele tabel: actieve rij (eenheid=source, parent=target)
    await db_session.execute(
        text(
            "INSERT INTO organisatie_eenheid_parent "
            "(eenheid_id, parent_id, geldig_van) VALUES (:e, :p, :v)"
        ),
        {"e": handmatig.id, "p": tooi.id, "v": date.today()},
    )
    await db_session.flush()

    resp = await client.post(f"/api/admin/reconciliation/{rec.id}/merge")
    assert resp.status_code == 200, resp.text

    # organisatie_eenheid.parent_id mag niet naar zichzelf wijzen
    row = (
        await db_session.execute(
            text("SELECT parent_id FROM organisatie_eenheid WHERE id = :t"),
            {"t": tooi.id},
        )
    ).first()
    assert row.parent_id != tooi.id, "self-loop in organisatie_eenheid.parent_id!"

    # organisatie_eenheid_parent mag geen self-loop bevatten
    self_loops = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) AS n FROM organisatie_eenheid_parent "
                "WHERE eenheid_id = parent_id"
            ),
        )
    ).first()
    assert self_loops.n == 0, (
        f"{self_loops.n} self-loops in organisatie_eenheid_parent!"
    )


async def test_reconciliation_merge_dedup_stakeholder_assessment(
    client, db_session: AsyncSession, reconciliation_setup, sample_person
):
    """Regressie C14: stakeholder_assessment heeft unique
    (person_id, scope_type, scope_id). Als persoon assessment heeft op
    zowel source als target eenheid, mag UPDATE niet violaten.
    """
    from sqlalchemy import text

    handmatig = reconciliation_setup["handmatig"]
    tooi = reconciliation_setup["tooi"]
    rec = reconciliation_setup["rec"]

    # Twee assessments voor dezelfde persoon — één op source, één op target
    for scope_id, belang in [(handmatig.id, 3), (tooi.id, 5)]:
        await db_session.execute(
            text(
                "INSERT INTO stakeholder_assessment "
                "(person_id, scope_type, scope_id, belang) "
                "VALUES (:p, 'organisatie_eenheid', :s, :b)"
            ),
            {"p": sample_person.id, "s": scope_id, "b": belang},
        )
    await db_session.flush()

    resp = await client.post(f"/api/admin/reconciliation/{rec.id}/merge")
    assert resp.status_code == 200, resp.text

    # Verwacht: één assessment op target (target's eigen overleeft, source's
    # wordt gededupeerd). Geen unique-violation, geen orphan op source.
    rows = (
        await db_session.execute(
            text(
                "SELECT scope_id, belang FROM stakeholder_assessment "
                "WHERE person_id = :p AND scope_type = 'organisatie_eenheid'"
            ),
            {"p": sample_person.id},
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].scope_id == tooi.id
    assert rows[0].belang == 5  # Target's eigen waarde behouden
