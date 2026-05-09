"""Tests voor onderwijsinstellingen + historische-kabinetten YAML-syncs."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.services.historische_kabinetten_sync import (
    sync_historische_kabinetten,
)
from bouwmeester.services.onderwijsinstellingen_sync import (
    sync_onderwijsinstellingen,
)


@pytest.fixture
async def schone_org_db(db_session: AsyncSession):
    """Verwijder TOOI-rijen + plaatsingen voor isolated test."""
    await db_session.execute(text("DELETE FROM person_organisatie_eenheid"))
    await db_session.execute(text("DELETE FROM person WHERE bron != 'handmatig'"))
    await db_session.execute(text("DELETE FROM organisatie_eenheid WHERE bron='tooi'"))
    await db_session.flush()


@pytest.fixture
async def synth_onderwijs(db_session: AsyncSession, schone_org_db):
    bestaand = (
        (
            await db_session.execute(
                select(OrganisatieEenheid).where(
                    OrganisatieEenheid.bron == "synthetisch",
                    OrganisatieEenheid.naam == "Onderwijsinstellingen",
                )
            )
        )
        .scalars()
        .first()
    )
    if bestaand is None:
        bestaand = OrganisatieEenheid(
            naam="Onderwijsinstellingen",
            type="synthetische_groep",
            bron="synthetisch",
        )
        db_session.add(bestaand)
        await db_session.flush()
    return bestaand


async def test_onderwijssync_minimal_yaml(
    db_session: AsyncSession, synth_onderwijs, tmp_path
):
    """Drie items toegevoegd; tweede run is idempotent."""
    yaml_path = tmp_path / "onderwijs.yaml"
    yaml_path.write_text(
        "universiteiten:\n"
        '  - {naam: "Test Universiteit", afkorting: "TU"}\n'
        "hogescholen:\n"
        '  - {naam: "Test Hogeschool", afkorting: "TH"}\n'
        '  - {naam: "Andere Hogeschool", afkorting: "AH"}\n'
    )
    s1 = await sync_onderwijsinstellingen(db_session, yaml_path, commit=False)
    assert s1.nieuwe_universiteiten == 1
    assert s1.nieuwe_hogescholen == 2

    s2 = await sync_onderwijsinstellingen(db_session, yaml_path, commit=False)
    assert s2.nieuwe_universiteiten == 0
    assert s2.nieuwe_hogescholen == 0
    assert s2.onveranderd == 3


async def test_onderwijssync_zonder_synth_groep_geeft_fout(
    db_session: AsyncSession, schone_org_db, tmp_path
):
    """Als synthetische 'Onderwijsinstellingen' ontbreekt, returns fout."""
    # Eerst eventuele children verwijderen, dan synth
    await db_session.execute(
        text(
            "DELETE FROM organisatie_eenheid WHERE parent_id IN ("
            "  SELECT id FROM organisatie_eenheid "
            "  WHERE bron='synthetisch' AND naam='Onderwijsinstellingen'"
            ")"
        )
    )
    await db_session.execute(
        text(
            "DELETE FROM organisatie_eenheid "
            "WHERE bron='synthetisch' AND naam='Onderwijsinstellingen'"
        )
    )
    await db_session.flush()

    yaml_path = tmp_path / "onderwijs.yaml"
    yaml_path.write_text(
        "universiteiten:\n  - {naam: 'X', afkorting: 'X'}\nhogescholen: []\n"
    )
    stats = await sync_onderwijsinstellingen(db_session, yaml_path, commit=False)
    assert stats.nieuwe_universiteiten == 0
    assert any("Onderwijsinstellingen" in f for f in stats.fouten)


async def test_historisch_kabinet_basic(
    db_session: AsyncSession, schone_org_db, tmp_path
):
    """Basis kabinet-import: 2 bewindspersonen krijgen plaatsingen met van/tot."""
    # Setup: ministerie met TOOI-URI
    bzk = OrganisatieEenheid(
        naam="ministerie van Binnenlandse Zaken en Koninkrijksrelaties",
        type="ministerie",
        bron="tooi",
        tooi_uri="https://identifier.overheid.nl/tooi/id/ministerie/mnre1034",
    )
    db_session.add(bzk)
    await db_session.flush()

    yaml_path = tmp_path / "kab.yaml"
    yaml_path.write_text(
        "kabinet_test:\n"
        "  van: 2024-01-01\n"
        "  tot: 2025-12-31\n"
        "  bewindspersonen:\n"
        '    - naam: "Anne Tester"\n'
        "      functie: minister\n"
        '      ministerie_tooi_uri: "https://identifier.overheid.nl/tooi/id/ministerie/mnre1034"\n'  # noqa: E501
        '      functietitel: "Minister van BZK"\n'
        '    - naam: "Bob Voorbeeld"\n'
        "      functie: staatssecretaris\n"
        '      ministerie_tooi_uri: "https://identifier.overheid.nl/tooi/id/ministerie/mnre1034"\n'  # noqa: E501
        '      functietitel: "Staatssecretaris van BZK"\n'
    )
    stats = await sync_historische_kabinetten(db_session, yaml_path, commit=False)
    assert stats.nieuwe_personen == 2
    assert stats.nieuwe_plaatsingen == 2

    # Verifieer plaatsing met juiste van/tot
    plc = (
        (
            await db_session.execute(
                select(PersonOrganisatieEenheid)
                .join(Person, Person.id == PersonOrganisatieEenheid.person_id)
                .where(Person.naam == "Anne Tester")
            )
        )
        .scalars()
        .first()
    )
    assert plc is not None
    assert plc.start_datum == date(2024, 1, 1)
    assert plc.eind_datum == date(2025, 12, 31)
    assert plc.functietitel == "Minister van BZK"


async def test_historisch_kabinet_idempotent(
    db_session: AsyncSession, schone_org_db, tmp_path
):
    """Tweede run met dezelfde YAML: 0 nieuwe plaatsingen."""
    bzk = OrganisatieEenheid(
        naam="ministerie van Binnenlandse Zaken en Koninkrijksrelaties",
        type="ministerie",
        bron="tooi",
        tooi_uri="https://identifier.overheid.nl/tooi/id/ministerie/mnre1034",
    )
    db_session.add(bzk)
    await db_session.flush()

    yaml_path = tmp_path / "kab.yaml"
    yaml_path.write_text(
        "kabinet_test:\n"
        "  van: 2024-01-01\n"
        "  tot: 2025-12-31\n"
        "  bewindspersonen:\n"
        '    - naam: "Anne Tester"\n'
        "      functie: minister\n"
        '      ministerie_tooi_uri: "https://identifier.overheid.nl/tooi/id/ministerie/mnre1034"\n'  # noqa: E501
        '      functietitel: "Minister"\n'
    )
    s1 = await sync_historische_kabinetten(db_session, yaml_path, commit=False)
    s2 = await sync_historische_kabinetten(db_session, yaml_path, commit=False)
    assert s1.nieuwe_plaatsingen == 1
    assert s2.nieuwe_plaatsingen == 0
    assert s2.onveranderd == 1


async def test_historisch_kabinet_skip_zonder_tooi_uri(
    db_session: AsyncSession, schone_org_db, tmp_path
):
    """Bewindspersoon met onbekende tooi_uri produceert fout, geen plaatsing."""
    yaml_path = tmp_path / "kab.yaml"
    yaml_path.write_text(
        "kabinet_test:\n"
        "  van: 2024-01-01\n"
        "  tot: 2025-12-31\n"
        "  bewindspersonen:\n"
        '    - naam: "Foo Bar"\n'
        "      functie: minister\n"
        '      ministerie_tooi_uri: "https://identifier.overheid.nl/tooi/id/ministerie/onbestaand"\n'  # noqa: E501
        '      functietitel: "Minister"\n'
    )
    stats = await sync_historische_kabinetten(db_session, yaml_path, commit=False)
    assert stats.nieuwe_plaatsingen == 0
    assert any("Geen OrganisatieEenheid" in f for f in stats.fouten)
