"""Regressietests voor uq_active_placement.

De index stond op (person_id, organisatie_eenheid_id) WHERE eind_datum IS
NULL, maar elke sync-service zoekt bestaande plaatsingen op gescoped per
``bron``. Zodra dezelfde persoon via twee bronnen actief was in dezelfde
eenheid — een Kamerlid dat bewindspersoon wordt is precies dat geval —
knalde de insert met een UniqueViolationError en sloeg de dagelijkse
overheidsorganisaties-sync om.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid


async def _person(session, naam: str) -> Person:
    person = Person(naam=naam)
    session.add(person)
    await session.flush()
    return person


async def _eenheid(session, naam: str) -> OrganisatieEenheid:
    eenheid = OrganisatieEenheid(naam=naam, type="Ministerie")
    session.add(eenheid)
    await session.flush()
    return eenheid


def _plaatsing(person, eenheid, bron: str, **kwargs) -> PersonOrganisatieEenheid:
    return PersonOrganisatieEenheid(
        person_id=person.id,
        organisatie_eenheid_id=eenheid.id,
        dienstverband="extern",
        bron=bron,
        start_datum=kwargs.pop("start_datum", date(2026, 1, 1)),
        **kwargs,
    )


@pytest.mark.asyncio
class TestActivePlacementUniqueness:
    async def test_two_sources_may_both_be_active(self, db_session):
        """Het productie-scenario: TK-lid wordt bewindspersoon.

        tk_odata en kabinet_yaml houden allebei een open plaatsing op
        dezelfde persoon+eenheid. Dat is geldige data, geen duplicaat.
        """
        person = await _person(db_session, f"Kamerlid {uuid.uuid4().hex[:6]}")
        eenheid = await _eenheid(db_session, f"Ministerie {uuid.uuid4().hex[:6]}")

        db_session.add(_plaatsing(person, eenheid, "tk_odata"))
        await db_session.flush()
        db_session.add(_plaatsing(person, eenheid, "kabinet_yaml"))
        # Voor de fix gooide deze flush een UniqueViolationError.
        await db_session.flush()

    async def test_same_source_twice_active_still_rejected(self, db_session):
        """Binnen één bron blijft 'één actieve plaatsing' gelden.

        Anders zou de index geen enkele duplicaat-bescherming meer bieden
        en kon een sync zijn eigen rijen blijven verdubbelen.
        """
        person = await _person(db_session, f"Ambtenaar {uuid.uuid4().hex[:6]}")
        eenheid = await _eenheid(db_session, f"Directie {uuid.uuid4().hex[:6]}")

        db_session.add(_plaatsing(person, eenheid, "abd_scrape"))
        await db_session.flush()
        db_session.add(_plaatsing(person, eenheid, "abd_scrape"))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_closed_placement_does_not_block_reappointment(self, db_session):
        """Een afgesloten rij telt niet mee: de index is partieel op
        eind_datum IS NULL. Iemand die terugkeert krijgt een nieuwe rij."""
        person = await _person(db_session, f"Terugkeerder {uuid.uuid4().hex[:6]}")
        eenheid = await _eenheid(db_session, f"Afdeling {uuid.uuid4().hex[:6]}")

        db_session.add(
            _plaatsing(
                person,
                eenheid,
                "abd_scrape",
                start_datum=date(2024, 1, 1),
                eind_datum=date(2025, 1, 1),
            )
        )
        await db_session.flush()
        db_session.add(
            _plaatsing(person, eenheid, "abd_scrape", start_datum=date(2026, 1, 1))
        )
        await db_session.flush()
