"""Regressietests voor plaatsingen bij het samenvoegen van eenheden.

``uq_active_placement`` staat per (person, eenheid, bron) maar één open rij
toe. De merge sluit daarom een open bron-rij af als de target er al een heeft.
Die check moet wél op dezelfde bron kijken: sinds de index bron-gescoped is
mogen een open tk_odata- en kabinet_yaml-plaatsing naast elkaar bestaan, en
die zonder bron-check afsluiten is stil historie-verlies.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.services.merge_organisatie_eenheden import (
    merge_organisatie_eenheden,
)


async def _eenheid(db_session, label: str) -> OrganisatieEenheid:
    eenheid = OrganisatieEenheid(
        naam=f"{label} {uuid.uuid4().hex[:8]}", type="Directie"
    )
    db_session.add(eenheid)
    await db_session.flush()
    return eenheid


async def _person(db_session) -> Person:
    person = Person(naam=f"Test Persoon {uuid.uuid4().hex[:6]}")
    db_session.add(person)
    await db_session.flush()
    return person


def _plaatsing(person, eenheid, bron, start, eind=None) -> PersonOrganisatieEenheid:
    return PersonOrganisatieEenheid(
        person_id=person.id,
        organisatie_eenheid_id=eenheid.id,
        dienstverband="extern",
        bron=bron,
        start_datum=start,
        eind_datum=eind,
    )


@pytest.mark.asyncio
async def test_merge_sluit_andere_bron_niet_af(db_session):
    """Open rijen van verschillende bronnen overleven de merge allebei."""
    source = await _eenheid(db_session, "Bron")
    target = await _eenheid(db_session, "Doel")
    person = await _person(db_session)

    db_session.add(_plaatsing(person, source, "abd_scrape", date(2025, 1, 1)))
    db_session.add(_plaatsing(person, target, "tk_odata", date(2024, 1, 1)))
    await db_session.flush()

    await merge_organisatie_eenheden(db_session, source.id, target.id)
    await db_session.flush()

    rows = (
        (
            await db_session.execute(
                select(PersonOrganisatieEenheid).where(
                    PersonOrganisatieEenheid.person_id == person.id,
                    PersonOrganisatieEenheid.organisatie_eenheid_id == target.id,
                )
            )
        )
        .scalars()
        .all()
    )
    open_per_bron = {r.bron: r for r in rows if r.eind_datum is None}
    # Beide bronnen horen nog open te staan; zonder bron-check werd
    # abd_scrape afgesloten omdat tk_odata toevallig open stond.
    assert set(open_per_bron) == {"abd_scrape", "tk_odata"}


@pytest.mark.asyncio
async def test_merge_sluit_zelfde_bron_wel_af(db_session):
    """Binnen dezelfde bron blijft er precies één open rij over."""
    source = await _eenheid(db_session, "Bron")
    target = await _eenheid(db_session, "Doel")
    person = await _person(db_session)

    db_session.add(_plaatsing(person, source, "tk_odata", date(2025, 1, 1)))
    db_session.add(_plaatsing(person, target, "tk_odata", date(2024, 1, 1)))
    await db_session.flush()

    await merge_organisatie_eenheden(db_session, source.id, target.id)
    # Zou zonder afsluiten botsen op uq_active_placement.
    await db_session.flush()

    rows = (
        (
            await db_session.execute(
                select(PersonOrganisatieEenheid).where(
                    PersonOrganisatieEenheid.person_id == person.id,
                    PersonOrganisatieEenheid.organisatie_eenheid_id == target.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len([r for r in rows if r.eind_datum is None]) == 1
