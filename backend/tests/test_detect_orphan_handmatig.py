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
    fcc = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="CJIB",
        type="uitvoeringsorganisatie",
        bron="handmatig",
        afkorting="CJIB",
    )
    tooi = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Centraal Justitieel Incassobureau",
        type="zbo",
        bron="tooi",
        tooi_uri="https://identifier.overheid.nl/tooi/id/test/cjib",
        afkorting="CJIB",
    )
    db_session.add_all([fcc, tooi])
    await db_session.flush()

    stats = await detect_orphan_handmatig_matches(db_session, commit=False)
    assert stats.found_match == 1
    assert stats.new_reconciliations == 1

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
    """Rij die al een tooi_uri heeft is geen orphan-handmatig."""
    al_gekoppeld = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Logius",
        type="zbo",
        bron="handmatig",
        tooi_uri="https://identifier.overheid.nl/tooi/id/test/logius",
        afkorting="Logius",
    )
    tooi = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Logius (TOOI)",
        type="zbo",
        bron="tooi",
        tooi_uri="https://identifier.overheid.nl/tooi/id/test/logius2",
        afkorting="Logius",
    )
    db_session.add_all([al_gekoppeld, tooi])
    await db_session.flush()

    stats = await detect_orphan_handmatig_matches(db_session, commit=False)
    assert stats.found_match == 0


async def test_orphan_skipt_reeds_open_reconciliation(
    db_session: AsyncSession, schone_pending
):
    """Tweede scan-run levert geen duplicate-pending."""
    fcc = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="DUO-rij",
        type="uitvoeringsorganisatie",
        bron="handmatig",
        afkorting="DUO",
    )
    tooi = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Dienst Uitvoering Onderwijs",
        type="agentschap",
        bron="tooi",
        tooi_uri="https://identifier.overheid.nl/tooi/id/test/duo",
        afkorting="DUO",
    )
    db_session.add_all([fcc, tooi])
    await db_session.flush()

    s1 = await detect_orphan_handmatig_matches(db_session, commit=False)
    assert s1.new_reconciliations == 1

    s2 = await detect_orphan_handmatig_matches(db_session, commit=False)
    assert s2.new_reconciliations == 0
    assert s2.already_pending == 1


async def test_orphan_match_op_genormaliseerde_naam(
    db_session: AsyncSession, schone_pending
):
    """Handmatig 'X' matcht TOOI 'agentschap X' via prefix-stripping."""
    fcc = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Telecom Beheer",
        type="uitvoeringsorganisatie",
        bron="handmatig",
    )
    tooi = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Agentschap Telecom Beheer",
        type="agentschap",
        bron="tooi",
        tooi_uri="https://identifier.overheid.nl/tooi/id/test/at",
    )
    db_session.add_all([fcc, tooi])
    await db_session.flush()

    stats = await detect_orphan_handmatig_matches(db_session, commit=False)
    assert stats.found_match == 1
    assert stats.new_reconciliations == 1
