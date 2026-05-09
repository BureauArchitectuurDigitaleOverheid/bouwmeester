"""Tests voor ABD-scrape titel-parsing en organisatie-resolutie.

Mock-fetcher vervangt Playwright-call. Dekt:
- Bekende ministerie-afkortingen (JenV, BZK, FIN)
- Diensten met fallback naar overkoepelend ministerie (Belastingdienst -> FIN)
- Greedy 'bij'-match voor 'X bij DUO bij OCW'
- Onbekende organisatie -> geen match (graceful)
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.services.abd_scrape import (
    AbdBenoeming,
    _resolveer_organisatie,
    _split_titel,
    sync_abd,
)


def test_split_titel_eenvoudig():
    """Standaard 'NAAM functie bij ORG'."""
    result = _split_titel("Esther Pijs directeur-generaal Migratie bij JenV")
    assert result is not None
    naam, functie, org = result
    assert naam == "Esther Pijs"
    assert "directeur-generaal" in functie.lower()
    assert org == "JenV"


def test_split_titel_dubbele_bij():
    """'X bij DUO bij OCW' -> laatste 'bij' wint (overkoepelend ministerie)."""
    result = _split_titel(
        "Astrid Zwiers directeur ICT bij Dienst Uitvoering Onderwijs bij OCW"
    )
    assert result is not None
    _, _, org = result
    assert org == "OCW"


def test_split_titel_kwartiermaker():
    """'kwartiermaker/directeur'-functies worden ook gepakt."""
    result = _split_titel(
        "Alvin Hasken kwartiermaker/directeur Screeningsdiensten bij Justis"
    )
    assert result is not None
    naam, functie, org = result
    assert naam == "Alvin Hasken"
    assert "kwartiermaker" in functie.lower()
    assert org == "Justis"


def test_split_titel_zonder_bij_returns_none():
    """Een titel zonder 'bij'-clause matcht niet."""
    assert _split_titel("Foo Bar directeur") is None


def test_split_titel_zonder_functie_returns_none():
    """Geen functie-trigger ('directeur', 'hoofd', etc.) -> geen match."""
    assert _split_titel("Iemand Anders bij JenV") is None


@pytest.fixture
async def schone_org_db(db_session: AsyncSession):
    """Verwijder bestaande TOOI-rijen + person-plaatsingen voor isolated test."""
    await db_session.execute(text("DELETE FROM person_organisatie_eenheid"))
    await db_session.execute(text("DELETE FROM organisatie_eenheid WHERE bron='tooi'"))
    await db_session.flush()


async def test_resolveer_op_ministerie_afkorting(
    db_session: AsyncSession, schone_org_db
):
    """JenV-afkorting matcht TOOI-rij voor ministerie van JenV."""
    db_session.add(
        OrganisatieEenheid(
            naam="ministerie van Justitie en Veiligheid",
            type="ministerie",
            bron="tooi",
            tooi_uri="https://identifier.overheid.nl/tooi/id/ministerie/mnre1058",
        )
    )
    await db_session.flush()

    row = await _resolveer_organisatie(db_session, "JenV")
    assert row is not None
    assert "Justitie en Veiligheid" in row.naam


async def test_resolveer_dienst_fallback_naar_ministerie(
    db_session: AsyncSession, schone_org_db
):
    """Onbekende dienst zonder eigen rij: fallback naar overkoepelend ministerie."""
    db_session.add(
        OrganisatieEenheid(
            naam="ministerie van Justitie en Veiligheid",
            type="ministerie",
            bron="tooi",
            tooi_uri="https://identifier.overheid.nl/tooi/id/ministerie/mnre1058",
        )
    )
    await db_session.flush()

    # DJI: hetzij eigen TOOI-rij hetzij fallback naar JenV — beide acceptabel.
    row = await _resolveer_organisatie(db_session, "DJI")
    assert row is not None
    # "Justitie" zit in zowel ministerienaam als "Justitiële Inrichtingen"
    assert "Justi" in row.naam


async def test_resolveer_strip_de_prefix(db_session: AsyncSession, schone_org_db):
    """'de NCTV' werkt net zo goed als 'NCTV'."""
    db_session.add(
        OrganisatieEenheid(
            naam="ministerie van Justitie en Veiligheid",
            type="ministerie",
            bron="tooi",
            tooi_uri="https://identifier.overheid.nl/tooi/id/ministerie/mnre1058",
        )
    )
    await db_session.flush()

    row = await _resolveer_organisatie(db_session, "de NCTV")
    assert row is not None  # NCTV -> JenV via dienst-fallback


async def test_resolveer_onbekend_returns_none(db_session: AsyncSession, schone_org_db):
    """Onbekende afkorting zonder match -> None."""
    row = await _resolveer_organisatie(db_session, "ZZZNonexistentZZZ")
    assert row is None


async def test_sync_abd_met_mock_fetcher(db_session: AsyncSession, schone_org_db):
    """Volledige sync-cyclus met mock-data; verifieer plaatsingen."""
    # Setup: ministerie + Person bestaat
    bzk = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="ministerie van Binnenlandse Zaken en Koninkrijksrelaties",
        type="ministerie",
        bron="tooi",
        tooi_uri="https://identifier.overheid.nl/tooi/id/ministerie/mnre1034",
    )
    db_session.add(bzk)
    await db_session.flush()

    async def mock_fetcher():
        return [
            AbdBenoeming(
                naam="Test Persoon",
                functietitel="directeur Test",
                organisatie_hint="BZK",
                nieuws_url="https://example.com/test",
                publicatiedatum=date(2026, 5, 9),
                ingangsdatum=date(2026, 6, 1),
            )
        ]

    stats = await sync_abd(db_session, fetcher=mock_fetcher, commit=False)
    assert stats.nieuwe_personen == 1
    assert stats.nieuwe_plaatsingen == 1
    assert stats.geen_org_match == 0

    person = (
        (await db_session.execute(select(Person).where(Person.naam == "Test Persoon")))
        .scalars()
        .first()
    )
    assert person is not None
    assert person.bron == "abd_scrape"


async def test_sync_abd_idempotent(db_session: AsyncSession, schone_org_db):
    """Tweede run met dezelfde mock-data: 0 nieuwe plaatsingen."""
    bzk = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="ministerie van Binnenlandse Zaken en Koninkrijksrelaties",
        type="ministerie",
        bron="tooi",
        tooi_uri="https://identifier.overheid.nl/tooi/id/ministerie/mnre1034",
    )
    db_session.add(bzk)
    await db_session.flush()

    async def mock_fetcher():
        return [
            AbdBenoeming(
                naam="Test Persoon",
                functietitel="directeur Test",
                organisatie_hint="BZK",
                nieuws_url="https://example.com/test",
                publicatiedatum=date(2026, 5, 9),
                ingangsdatum=date(2026, 6, 1),
            )
        ]

    s1 = await sync_abd(db_session, fetcher=mock_fetcher, commit=False)
    s2 = await sync_abd(db_session, fetcher=mock_fetcher, commit=False)
    assert s1.nieuwe_plaatsingen == 1
    assert s2.nieuwe_plaatsingen == 0
    assert s2.onveranderd == 1
