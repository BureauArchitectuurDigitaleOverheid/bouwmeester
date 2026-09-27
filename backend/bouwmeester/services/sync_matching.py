"""How an official sync finds the person and the eenheid an entry is about.

A placement from an official sync is trusted (``TRUSTED_PLACEMENT_BRONNEN``):
it gives access.  So a sync must never attach one to a person or an eenheid
a user controls.  Names are user-controlled: anyone may rename a contact, or
themselves, to an announced appointee.  The rules here:

- A person is only matched when a sync brought it: the sync's own ``bron``,
  or a TK person carrying its stable ``tk_persoon_id``.  Never an account
  (a login, an API key, an agent) and never a person with an email address
  (``Person.email`` or ``PersonEmail``), since an address is what a login
  claims a person by.  So a sync never writes an address itself.
- A name shared by several such persons is ambiguous: refused, not guessed.
- A name held only by persons the sync may not use gets a new person of the
  sync's own, and a ``conflict`` line in the sync log so an administrator
  can reconcile the two by hand.
- An eenheid is only matched among eenheden an official source brought, and
  only when exactly one matches.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_email import PersonEmail
from bouwmeester.models.tooi_sync_log import TooiSyncLog

# Eenheden brought by an official source; users create ``handmatig`` ones.
OFFICIAL_EENHEID_BRONNEN = frozenset({"tooi", "ministeries_csv", "organogram_scrape"})

# TK persons carry a stable external key; only those are matched.
_TK_BRON = "tk_odata"


@dataclass
class PersonMatch:
    """The outcome of :func:`match_sync_person`."""

    person: Person | None = None
    ambiguous: bool = False
    # Persons with the name the sync may not attach anything to.
    passed_over: int = 0
    created: bool = False

    def ambiguity(self, naam: str) -> str:
        """The error line for a refused, ambiguous name."""
        return (
            f"Meerdere personen met de naam '{naam}' komen in aanmerking; "
            "niet gekoppeld"
        )


async def _with_emails(db: AsyncSession, ids: Collection[uuid.UUID]) -> set[uuid.UUID]:
    if not ids:
        return set()
    rows = await db.execute(
        select(PersonEmail.person_id).where(PersonEmail.person_id.in_(ids)).distinct()
    )
    return set(rows.scalars().all())


def _brought_by_sync(person: Person, bronnen: Collection[str]) -> bool:
    if person.bron == _TK_BRON:
        return _TK_BRON in bronnen and person.tk_persoon_id is not None
    return person.bron in bronnen


def _is_account(person: Person) -> bool:
    return bool(
        person.oidc_subject
        or person.oidc_email
        or person.api_key_hash
        or person.is_agent
        or person.email
    )


async def usable_by_sync(
    db: AsyncSession, persons: list[Person], bronnen: Collection[str]
) -> list[Person]:
    """The persons of *persons* a sync of *bronnen* may place (see above)."""
    usable = [p for p in persons if _brought_by_sync(p, bronnen) and not _is_account(p)]
    emails = await _with_emails(db, [p.id for p in usable])
    return [p for p in usable if p.id not in emails]


async def match_sync_person(
    db: AsyncSession, naam: str, *, bronnen: Collection[str], where=None
) -> PersonMatch:
    """The one person named *naam* a sync of *bronnen* may place.

    *where* narrows the name match further (an SQL clause); without it the
    name must match exactly.
    """
    clause = Person.naam == naam if where is None else where
    candidates = list(
        (await db.execute(select(Person).where(clause).order_by(Person.id)))
        .scalars()
        .all()
    )
    eligible = await usable_by_sync(db, candidates, bronnen)
    passed_over = len(candidates) - len(eligible)
    if len(eligible) > 1:
        return PersonMatch(ambiguous=True, passed_over=passed_over)
    return PersonMatch(
        person=eligible[0] if eligible else None, passed_over=passed_over
    )


async def person_for_sync(
    db: AsyncSession,
    naam: str,
    *,
    bron: str,
    sync_run_id: uuid.UUID,
    log_bron: str,
    also: Collection[str] = (),
) -> PersonMatch:
    """The person a sync of *bron* places for *naam*, created when needed.

    ``person`` is None only when the name is ambiguous.  *also* are further
    ``bron`` values whose persons may be reused (``tk_odata``: by its
    stable key).
    """
    match = await match_sync_person(db, naam, bronnen={bron, *also})
    if match.ambiguous or match.person is not None:
        return match
    return await create_sync_person(
        db, naam, bron=bron, sync_run_id=sync_run_id, log_bron=log_bron, match=match
    )


async def create_sync_person(
    db: AsyncSession,
    naam: str,
    *,
    bron: str,
    sync_run_id: uuid.UUID,
    log_bron: str,
    match: PersonMatch,
) -> PersonMatch:
    """A new person of the sync for an unmatched *match*.

    Created next to same-named persons the sync may not use, it is logged
    as a ``conflict`` for reconciliation.
    """
    person = Person(naam=naam, bron=bron)
    db.add(person)
    await db.flush()
    if match.passed_over:
        _log_passed_over(db, sync_run_id, log_bron, person, match.passed_over)
    return PersonMatch(person=person, passed_over=match.passed_over, created=True)


def _log_passed_over(
    db: AsyncSession,
    sync_run_id: uuid.UUID,
    log_bron: str,
    person: Person,
    passed_over: int,
) -> None:
    """Record that *person* was created next to same-named persons."""
    naam = person.naam
    db.add(
        TooiSyncLog(
            sync_run_id=sync_run_id,
            bron=log_bron,
            action="conflict",
            person_id=person.id,
            note=(
                f"nieuwe persoon '{naam}' aangemaakt naast {passed_over} "
                "bestaande persoon/personen met dezelfde naam die de sync niet "
                "zelf bracht; controleer handmatig of het dezelfde persoon is"
            ),
        )
    )


async def find_official_eenheid(db: AsyncSession, *where) -> OrganisatieEenheid | None:
    """The one active official eenheid matching *where*, or None.

    None as well when several match: a sync does not guess.
    """
    rows = (
        (
            await db.execute(
                select(OrganisatieEenheid)
                .where(
                    OrganisatieEenheid.bron.in_(OFFICIAL_EENHEID_BRONNEN),
                    OrganisatieEenheid.geldig_tot.is_(None),
                    *where,
                )
                .limit(2)
            )
        )
        .scalars()
        .all()
    )
    return rows[0] if len(rows) == 1 else None
