"""Tests voor detect_orphan_handmatig: vind FCC-rijen die alsnog op TOOI matchen."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.pending_reconciliation import PendingReconciliation
from bouwmeester.services.detect_orphan_handmatig import (
    detect_orphan_handmatig_matches,
)


@pytest.fixture
async def schone_pending(db_session: AsyncSession):
    from sqlalchemy import text

    await db_session.execute(text("DELETE FROM pending_reconciliation"))
    await db_session.flush()


async def test_orphan_match_op_afkorting_genereert_reconciliation(
    db_session: AsyncSession, schone_pending
):
    """FCC-rij 'CJIB' afk='CJIB' -> match TOOI 'Centraal Justitieel...' afk='CJIB'."""
    # Unieke afkorting voorkomt botsing met seed-data in CI.
    fcc = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="CJIB-test-rij",
        type="uitvoeringsorganisatie",
        bron="handmatig",
        afkorting="CJIB-XYZ",
    )
    tooi = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Centraal Justitieel Incassobureau (test)",
        type="zbo",
        bron="tooi",
        tooi_uri="https://identifier.overheid.nl/tooi/id/test/cjib-xyz",
        afkorting="CJIB-XYZ",
    )
    db_session.add_all([fcc, tooi])
    await db_session.flush()

    await detect_orphan_handmatig_matches(db_session, commit=False)

    rec = (
        (
            await db_session.execute(
                select(PendingReconciliation).where(
                    PendingReconciliation.handmatige_id == fcc.id
                )
            )
        )
        .scalars()
        .first()
    )
    assert rec is not None
    assert rec.kandidaat_id == tooi.id
    assert rec.match_reden == "afkorting_ci"


async def test_orphan_skipt_rijen_met_tooi_uri(
    db_session: AsyncSession, schone_pending
):
    """Rij die al een tooi_uri heeft is geen orphan-handmatig.

    Verifieerd door te checken dat geen reconciliation-rij naar deze
    handmatige rij wijst — globaal found_match-aantal kan groter zijn
    door seed-data met andere matches.
    """
    al_gekoppeld = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Logius",
        type="zbo",
        bron="handmatig",
        tooi_uri="https://identifier.overheid.nl/tooi/id/test/logius",
        afkorting="Logius-test-skip",
    )
    tooi = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Logius (TOOI)",
        type="zbo",
        bron="tooi",
        tooi_uri="https://identifier.overheid.nl/tooi/id/test/logius2",
        afkorting="Logius-test-skip",
    )
    db_session.add_all([al_gekoppeld, tooi])
    await db_session.flush()

    await detect_orphan_handmatig_matches(db_session, commit=False)

    rec_voor_deze_rij = (
        (
            await db_session.execute(
                select(PendingReconciliation).where(
                    PendingReconciliation.handmatige_id == al_gekoppeld.id
                )
            )
        )
        .scalars()
        .first()
    )
    assert rec_voor_deze_rij is None


async def test_orphan_skipt_reeds_open_reconciliation(
    db_session: AsyncSession, schone_pending
):
    """Tweede scan-run levert geen duplicate-pending."""
    fcc = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="DUO-rij-test",
        type="uitvoeringsorganisatie",
        bron="handmatig",
        afkorting="DUO-test-idem",
    )
    tooi = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Dienst Uitvoering Onderwijs (test)",
        type="agentschap",
        bron="tooi",
        tooi_uri="https://identifier.overheid.nl/tooi/id/test/duo-test",
        afkorting="DUO-test-idem",
    )
    db_session.add_all([fcc, tooi])
    await db_session.flush()

    await detect_orphan_handmatig_matches(db_session, commit=False)
    rec1 = (
        (
            await db_session.execute(
                select(PendingReconciliation).where(
                    PendingReconciliation.handmatige_id == fcc.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rec1) == 1

    # Tweede run: geen tweede rij voor dezelfde handmatige id.
    await detect_orphan_handmatig_matches(db_session, commit=False)
    rec2 = (
        (
            await db_session.execute(
                select(PendingReconciliation).where(
                    PendingReconciliation.handmatige_id == fcc.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rec2) == 1


async def test_orphan_match_op_organogram_bron(
    db_session: AsyncSession, schone_pending
):
    """Kandidaat mag ook uit organogram_scrape komen, niet alleen tooi.

    Dit is de DGDOO-case: seed-DG 'DG X' (handmatig) naast een
    organogram-scrape-rij 'X' — een tooi-only kandidaatfilter zag dat
    nooit en liet het duplicaat staan.
    """
    seed_dg = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="DG Digitalisering-test-Overheidsorg",
        type="directoraat_generaal",
        bron="handmatig",
    )
    organogram = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Digitalisering-test-Overheidsorg",
        type="directoraat_generaal",
        bron="organogram_scrape",
    )
    db_session.add_all([seed_dg, organogram])
    await db_session.flush()

    await detect_orphan_handmatig_matches(db_session, commit=False)

    rec = (
        (
            await db_session.execute(
                select(PendingReconciliation).where(
                    PendingReconciliation.handmatige_id == seed_dg.id
                )
            )
        )
        .scalars()
        .first()
    )
    assert rec is not None
    assert rec.kandidaat_id == organogram.id
    assert rec.kandidaat_bron == "organogram_scrape"
    assert rec.match_reden == "naam_normalized"


async def test_orphan_match_op_genormaliseerde_naam(
    db_session: AsyncSession, schone_pending
):
    """Handmatig 'X' matcht TOOI 'agentschap X' via prefix-stripping."""
    fcc = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Test-Naam-Match-Beheer",
        type="uitvoeringsorganisatie",
        bron="handmatig",
    )
    tooi = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Agentschap Test-Naam-Match-Beheer",
        type="agentschap",
        bron="tooi",
        tooi_uri="https://identifier.overheid.nl/tooi/id/test/at-test",
    )
    db_session.add_all([fcc, tooi])
    await db_session.flush()

    await detect_orphan_handmatig_matches(db_session, commit=False)

    rec = (
        (
            await db_session.execute(
                select(PendingReconciliation).where(
                    PendingReconciliation.handmatige_id == fcc.id
                )
            )
        )
        .scalars()
        .first()
    )
    assert rec is not None
    assert rec.kandidaat_id == tooi.id
    assert rec.match_reden == "naam_normalized"
