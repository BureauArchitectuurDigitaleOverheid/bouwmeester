"""Official syncs never hand a trusted placement to a user-controlled record.

A placement from the ABD scrape or the kabinet syncs gives access, and names
are user-controlled.  Renaming yourself (or a contact carrying your address)
to an announced appointee must not put you in the ministerie; a user-made
eenheid with a matching name must not receive an official placement.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_email import PersonEmail
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.tooi_sync_log import TooiSyncLog
from bouwmeester.services.abd_scrape import (
    AbdBenoeming,
    _resolveer_organisatie,
    sync_abd,
)
from bouwmeester.services.historische_kabinetten_sync import (
    sync_historische_kabinetten,
)
from bouwmeester.services.kabinet_sync import sync_kabinet

BZK_URI = "https://identifier.overheid.nl/tooi/id/ministerie/mnre1034"
NAAM = "Aangekondigde Benoemde"


@pytest.fixture
async def bzk(db_session: AsyncSession) -> OrganisatieEenheid:
    await db_session.execute(text("DELETE FROM person_organisatie_eenheid"))
    await db_session.execute(text("DELETE FROM organisatie_eenheid WHERE bron='tooi'"))
    eenheid = OrganisatieEenheid(
        naam="ministerie van Binnenlandse Zaken en Koninkrijksrelaties",
        type="ministerie",
        bron="tooi",
        tooi_uri=BZK_URI,
    )
    db_session.add(eenheid)
    await db_session.flush()
    return eenheid


async def _account(db: AsyncSession, **extra) -> Person:
    """A logged-in user who renamed themselves to the appointee."""
    person = Person(naam=NAAM, oidc_subject=f"sub-{uuid.uuid4()}", **extra)
    db.add(person)
    await db.flush()
    return person


async def _contact_with_address(db: AsyncSession) -> Person:
    """A plain contact carrying the attacker's address, renamed likewise."""
    person = Person(naam=NAAM)
    db.add(person)
    await db.flush()
    db.add(PersonEmail(person_id=person.id, email="aanvaller@example.org"))
    await db.flush()
    return person


async def _placements(db: AsyncSession, person_id: uuid.UUID) -> list:
    rows = await db.execute(
        select(PersonOrganisatieEenheid).where(
            PersonOrganisatieEenheid.person_id == person_id
        )
    )
    return list(rows.scalars().all())


async def _synced_persons(db: AsyncSession, bron: str) -> list[Person]:
    rows = await db.execute(
        select(Person).where(Person.naam == NAAM, Person.bron == bron)
    )
    return list(rows.scalars().all())


def _benoeming(naam: str = NAAM, hint: str = "BZK") -> AbdBenoeming:
    return AbdBenoeming(
        naam=naam,
        functietitel="directeur-generaal",
        organisatie_hint=hint,
        nieuws_url="https://example.com/benoeming",
        publicatiedatum=date(2026, 5, 9),
        ingangsdatum=date(2026, 6, 1),
    )


def _fetcher(*benoemingen: AbdBenoeming):
    async def fetch():
        return list(benoemingen)

    return fetch


def _kabinet_yaml(tmp_path, naam: str = NAAM):
    path = tmp_path / "kabinet.yaml"
    path.write_text(
        "bewindspersonen:\n"
        f'  - naam: "{naam}"\n'
        f'    ministerie_tooi_uri: "{BZK_URI}"\n'
        '    functietitel: "Minister van BZK"\n'
        "    van: 2026-01-01\n"
    )
    return path


def _historisch_yaml(tmp_path, naam: str = NAAM):
    path = tmp_path / "historisch.yaml"
    path.write_text(
        "kabinet_test:\n"
        "  van: 2024-01-01\n"
        "  tot: 2025-12-31\n"
        "  bewindspersonen:\n"
        f'    - naam: "{naam}"\n'
        f'      ministerie_tooi_uri: "{BZK_URI}"\n'
        '      functietitel: "Minister"\n'
    )
    return path


async def _run(kind: str, db: AsyncSession, tmp_path, naam: str = NAAM):
    if kind == "abd":
        return await sync_abd(db, fetcher=_fetcher(_benoeming(naam)), commit=False)
    if kind == "kabinet":
        return await sync_kabinet(db, _kabinet_yaml(tmp_path, naam))
    return await sync_historische_kabinetten(
        db, _historisch_yaml(tmp_path, naam), commit=False
    )


_BRON = {"abd": "abd_scrape", "kabinet": "kabinet_yaml", "historisch": "kabinet_yaml"}
_SYNCS = ["abd", "kabinet", "historisch"]


@pytest.mark.parametrize("kind", _SYNCS)
@pytest.mark.parametrize("make", [_account, _contact_with_address])
async def test_renamed_record_gets_no_trusted_placement(
    db_session: AsyncSession, bzk, tmp_path, kind, make
):
    victim = await make(db_session)

    await _run(kind, db_session, tmp_path)

    assert await _placements(db_session, victim.id) == []
    [created] = await _synced_persons(db_session, _BRON[kind])
    assert created.id != victim.id
    [placement] = await _placements(db_session, created.id)
    assert placement.organisatie_eenheid_id == bzk.id
    conflict = await db_session.execute(
        select(TooiSyncLog).where(
            TooiSyncLog.person_id == created.id, TooiSyncLog.action == "conflict"
        )
    )
    assert conflict.scalars().first() is not None


@pytest.mark.parametrize("kind", _SYNCS)
async def test_second_run_reuses_the_synced_person(
    db_session: AsyncSession, bzk, tmp_path, kind
):
    await _account(db_session)
    await _run(kind, db_session, tmp_path)
    await _run(kind, db_session, tmp_path)

    assert len(await _synced_persons(db_session, _BRON[kind])) == 1


@pytest.mark.parametrize("kind", _SYNCS)
async def test_ambiguous_name_is_refused(db_session: AsyncSession, bzk, tmp_path, kind):
    for _ in range(2):
        db_session.add(Person(naam=NAAM, bron=_BRON[kind]))
    await db_session.flush()

    stats = await _run(kind, db_session, tmp_path)

    assert stats.new_placements == 0
    assert any("meerdere" in f.lower() for f in stats.fouten)
    assert len(await _synced_persons(db_session, _BRON[kind])) == 2


async def test_kabinet_merges_into_tk_person_by_key(
    db_session: AsyncSession, bzk, tmp_path
):
    """An ex-Kamerlid synced from TK (stable key) is still reused."""
    tk = Person(naam=NAAM, bron="tk_odata", tk_persoon_id=str(uuid.uuid4()))
    db_session.add(tk)
    await db_session.flush()

    await _run("kabinet", db_session, tmp_path)

    assert len(await _placements(db_session, tk.id)) == 1


async def test_kabinet_surname_match_skips_tk_account(
    db_session: AsyncSession, bzk, tmp_path
):
    tk = Person(
        naam="Aangekondigde Tussen Benoemde",
        bron="tk_odata",
        tk_persoon_id=str(uuid.uuid4()),
        oidc_subject=f"sub-{uuid.uuid4()}",
    )
    db_session.add(tk)
    await db_session.flush()

    await _run("kabinet", db_session, tmp_path)

    assert await _placements(db_session, tk.id) == []


async def test_resolver_ignores_user_made_eenheid(db_session: AsyncSession, bzk):
    """A handmatig eenheid named like a dienst gets no official placement."""
    db_session.add(
        OrganisatieEenheid(naam="Dienst Uitvoering Onderwijs", type="dienst")
    )
    await db_session.flush()

    assert await _resolveer_organisatie(db_session, "DUO") is None


async def test_resolver_refuses_ambiguous_match(db_session: AsyncSession, bzk):
    for naam in ("Rijksdienst Een", "Rijksdienst Twee"):
        db_session.add(OrganisatieEenheid(naam=naam, type="dienst", bron="tooi"))
    await db_session.flush()

    assert await _resolveer_organisatie(db_session, "Rijksdienst") is None


async def test_resolver_treats_hint_as_literal(db_session: AsyncSession, bzk):
    assert await _resolveer_organisatie(db_session, "%") is None
