"""Regressietests voor botsende open plaatsingen in de TK-sync.

uq_active_placement staat per (person, eenheid, bron) maar één open rij toe.
De TK-feed kan op twee manieren een tweede open rij uitlokken:

1. Twee zetel-records zonder TotEnMet voor dezelfde persoon.
2. Een upstream-correctie die TotEnMet weghaalt, waardoor een afgesloten rij
   heropent terwijl er al een andere open rij staat.

Beide sloegen de dagelijkse sync om met een UniqueViolationError.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.tooi_sync_log import TooiSyncLog
from bouwmeester.services import tk_persoon_sync
from bouwmeester.services.tk_persoon_sync import (
    TkSyncStats,
    _existing_persons_by_tk_id,
    _sync_tk,
)

_tk_persons = _existing_persons_by_tk_id


async def _setup(db_session, monkeypatch) -> tuple[OrganisatieEenheid, Person, str]:
    """Maak een eigen TK-eenheid en wijs de service daarnaar.

    ``_sync_tk`` zoekt de eenheid op ``TK_EENHEID_NAAM``. Een gedeelde
    "Tweede Kamer"-rij hergebruiken maakt de assertions afhankelijk van wat
    andere tests of de seed daar hebben achtergelaten, dus geven we deze test
    een unieke eigen eenheid.
    """
    naam = f"Tweede Kamer {uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(tk_persoon_sync, "TK_EENHEID_NAAM", naam)

    eenheid = OrganisatieEenheid(naam=naam, type="overig", bron="tooi")
    db_session.add(eenheid)
    await db_session.flush()

    tk_id = uuid.uuid4().hex[:8]
    person = Person(naam="Test Kamerlid", bron="tk_odata", tk_persoon_id=tk_id)
    db_session.add(person)
    await db_session.flush()
    return eenheid, person, tk_id


def _record(tk_id: str, van: str, tot: str | None) -> dict:
    return {
        "Id": f"rec-{van}",
        "Van": van,
        "TotEnMet": tot,
        "Persoon": {"Id": tk_id, "Roepnaam": "Test", "Achternaam": "Kamerlid"},
        "FractieZetel": {"Fractie": {"Afkorting": "X"}},
    }


async def _rijen(db_session, eenheid_id, person_id) -> list[PersonOrganisatieEenheid]:
    """Alleen de rijen van deze testpersoon in deze eenheid."""
    return list(
        (
            await db_session.execute(
                select(PersonOrganisatieEenheid).where(
                    PersonOrganisatieEenheid.organisatie_eenheid_id == eenheid_id,
                    PersonOrganisatieEenheid.person_id == person_id,
                )
            )
        )
        .scalars()
        .all()
    )


async def _open_rijen(db_session, eenheid_id, person_id):
    rows = await _rijen(db_session, eenheid_id, person_id)
    return [r for r in rows if r.eind_datum is None]


@pytest.mark.asyncio
async def test_twee_open_feed_records_geven_een_open_rij(db_session, monkeypatch):
    """Twee zetel-records zonder TotEnMet mogen niet botsen."""
    eenheid, person, tk_id = await _setup(db_session, monkeypatch)

    async def fetcher():
        return [
            _record(tk_id, "2023-01-01", None),
            _record(tk_id, "2024-01-02", None),
        ]

    stats = TkSyncStats(sync_run_id=uuid.uuid4())
    await _sync_tk(
        db_session, uuid.uuid4(), fetcher, await _tk_persons(db_session), stats
    )
    await db_session.flush()

    open_rijen = await _open_rijen(db_session, eenheid.id, person.id)
    assert len(open_rijen) == 1
    # De actuele termijn (nieuwste Van-datum) blijft open.
    assert open_rijen[0].start_datum == date(2024, 1, 2)


@pytest.mark.asyncio
async def test_heropende_rij_botst_niet_met_bestaande_open_rij(db_session, monkeypatch):
    """Upstream haalt TotEnMet weg bij een oude termijn.

    De afgesloten rij zou heropenen terwijl de huidige termijn al open is.
    """
    eenheid, person, tk_id = await _setup(db_session, monkeypatch)

    db_session.add(
        PersonOrganisatieEenheid(
            person_id=person.id,
            organisatie_eenheid_id=eenheid.id,
            dienstverband="extern",
            bron="tk_odata",
            start_datum=date(2023, 1, 1),
            eind_datum=date(2024, 1, 1),
        )
    )
    db_session.add(
        PersonOrganisatieEenheid(
            person_id=person.id,
            organisatie_eenheid_id=eenheid.id,
            dienstverband="extern",
            bron="tk_odata",
            start_datum=date(2024, 1, 2),
            eind_datum=None,
        )
    )
    await db_session.flush()

    async def fetcher():
        return [
            _record(tk_id, "2023-01-01", None),  # correctie: geen einddatum meer
            _record(tk_id, "2024-01-02", None),
        ]

    stats = TkSyncStats(sync_run_id=uuid.uuid4())
    await _sync_tk(
        db_session, uuid.uuid4(), fetcher, await _tk_persons(db_session), stats
    )
    # Voor de fix gooide deze flush een UniqueViolationError.
    await db_session.flush()

    open_rijen = await _open_rijen(db_session, eenheid.id, person.id)
    assert len(open_rijen) == 1
    assert open_rijen[0].start_datum == date(2024, 1, 2)


@pytest.mark.asyncio
async def test_afgesloten_records_blijven_normaal_werken(db_session, monkeypatch):
    """Een normale feed met historie + huidige termijn blijft correct."""
    eenheid, person, tk_id = await _setup(db_session, monkeypatch)

    async def fetcher():
        return [
            _record(tk_id, "2021-03-31", "2023-12-05"),
            _record(tk_id, "2023-12-06", None),
        ]

    stats = TkSyncStats(sync_run_id=uuid.uuid4())
    await _sync_tk(
        db_session, uuid.uuid4(), fetcher, await _tk_persons(db_session), stats
    )
    await db_session.flush()

    rows = await _rijen(db_session, eenheid.id, person.id)
    assert len(rows) == 2
    assert len([r for r in rows if r.eind_datum is None]) == 1


# ---------------------------------------------------------------------------
# A trusted TK placement never lands on something a user controls (round 6)
# ---------------------------------------------------------------------------


async def test_user_created_tweede_kamer_is_not_used(db_session, monkeypatch):
    """Only an official eenheid of that name receives trusted placements."""
    eenheid, person, tk_id = await _setup(db_session, monkeypatch)
    eenheid.bron = "handmatig"
    await db_session.flush()

    async def fetcher():
        return [_record(tk_id, "2024-01-01", None)]

    stats = TkSyncStats(sync_run_id=uuid.uuid4())
    await _sync_tk(
        db_session, uuid.uuid4(), fetcher, await _tk_persons(db_session), stats
    )
    assert await _rijen(db_session, eenheid.id, person.id) == []
    assert stats.fouten


async def test_account_carrying_the_tk_key_gets_no_placement(db_session, monkeypatch):
    eenheid, person, tk_id = await _setup(db_session, monkeypatch)
    person.oidc_subject = f"sub-{uuid.uuid4().hex}"
    await db_session.flush()

    async def fetcher():
        return [_record(tk_id, "2024-01-01", None)]

    run = uuid.uuid4()
    stats = TkSyncStats(sync_run_id=run)
    await _sync_tk(db_session, run, fetcher, await _tk_persons(db_session), stats)
    await db_session.flush()

    assert await _rijen(db_session, eenheid.id, person.id) == []
    assert person.tk_persoon_id is None
    kamerlid = await db_session.scalar(
        select(Person).where(Person.tk_persoon_id == tk_id)
    )
    assert kamerlid is not None and kamerlid.id != person.id
    assert len(await _open_rijen(db_session, eenheid.id, kamerlid.id)) == 1
    conflict = await db_session.scalar(
        select(TooiSyncLog.id).where(
            TooiSyncLog.sync_run_id == run,
            TooiSyncLog.action == "conflict",
            TooiSyncLog.person_id == kamerlid.id,
        )
    )
    assert conflict is not None
