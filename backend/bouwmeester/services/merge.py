"""Person merge service — detect duplicates and merge persons."""

import logging
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.absence import Absence
from bouwmeester.models.activity import Activity
from bouwmeester.models.node_stakeholder import NodeStakeholder
from bouwmeester.models.notification import Notification
from bouwmeester.models.person import Person
from bouwmeester.models.person_email import PersonEmail
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.person_phone import PersonPhone
from bouwmeester.models.task import Task

logger = logging.getLogger(__name__)

# Known Rijksoverheid domain group — emails within this group are treated
# as potentially belonging to the same person.
RIJKSOVERHEID_DOMAINS = {
    "rijksoverheid.nl",
    "minbzk.nl",
    "minocw.nl",
    "minaz.nl",
    "minfin.nl",
    "mindef.nl",
    "minienw.nl",
    "minszw.nl",
    "minvws.nl",
    "buitenlandse-zaken.nl",
}


def _is_rijksoverheid_email(email: str) -> bool:
    """Check if email domain is in the Rijksoverheid domain group."""
    domain = email.rsplit("@", 1)[-1].lower()
    return domain in RIJKSOVERHEID_DOMAINS


async def find_merge_candidates(
    db: AsyncSession,
    person: Person,
) -> list[Person]:
    """Find persons with the same name whose email is in the Rijksoverheid group.

    Only returns candidates if the current person also has a Rijksoverheid email.
    """
    # Check if current person has a Rijksoverheid email
    person_emails = (
        (
            await db.execute(
                select(PersonEmail.email).where(PersonEmail.person_id == person.id)
            )
        )
        .scalars()
        .all()
    )

    # Also check legacy email
    all_emails = list(person_emails)
    if person.email and person.email not in all_emails:
        all_emails.append(person.email)

    has_rijksoverheid = any(_is_rijksoverheid_email(e) for e in all_emails)
    if not has_rijksoverheid:
        return []

    # Find persons with the same name (case-insensitive)
    from sqlalchemy import func
    from sqlalchemy.orm import selectinload

    stmt = (
        select(Person)
        .where(
            func.lower(func.trim(Person.naam)) == func.lower(func.trim(person.naam)),
            Person.id != person.id,
        )
        .options(selectinload(Person.emails), selectinload(Person.phones))
    )
    result = await db.execute(stmt)
    candidates = result.scalars().all()

    # Filter: candidate must also have at least one Rijksoverheid email
    filtered = []
    for c in candidates:
        candidate_emails = [e.email for e in c.emails]
        if c.email and c.email not in candidate_emails:
            candidate_emails.append(c.email)
        if any(_is_rijksoverheid_email(e) for e in candidate_emails):
            filtered.append(c)

    return filtered


async def merge_persons(
    db: AsyncSession,
    keep_id: UUID,
    absorb_id: UUID,
) -> Person:
    """Merge absorb person into keep person.

    Transfers all relationships from absorb to keep, then deletes absorb.
    Returns the updated keep person.
    """
    from sqlalchemy.orm import selectinload

    keep = await db.get(Person, keep_id)
    absorb = await db.get(Person, absorb_id)
    if keep is None or absorb is None:
        raise ValueError("Person not found")

    # Transfer oidc_subject if keep doesn't have one
    if not keep.oidc_subject and absorb.oidc_subject:
        oidc_value = absorb.oidc_subject
        absorb.oidc_subject = None  # clear first to avoid unique constraint
        await db.flush()
        keep.oidc_subject = oidc_value

    # Transfer emails (skip duplicates)
    absorb_emails = (
        (
            await db.execute(
                select(PersonEmail).where(PersonEmail.person_id == absorb_id)
            )
        )
        .scalars()
        .all()
    )
    for email_obj in absorb_emails:
        email_obj.person_id = keep_id
        email_obj.is_default = False  # keep's defaults stay

    # Transfer phones
    await db.execute(
        update(PersonPhone)
        .where(PersonPhone.person_id == absorb_id)
        .values(person_id=keep_id, is_default=False)
    )

    # Transfer tasks
    await db.execute(
        update(Task).where(Task.assignee_id == absorb_id).values(assignee_id=keep_id)
    )

    # Transfer stakeholder roles
    await db.execute(
        update(NodeStakeholder)
        .where(NodeStakeholder.person_id == absorb_id)
        .values(person_id=keep_id)
    )

    # Transfer org placements
    await db.execute(
        update(PersonOrganisatieEenheid)
        .where(PersonOrganisatieEenheid.person_id == absorb_id)
        .values(person_id=keep_id)
    )

    # Transfer activities
    await db.execute(
        update(Activity).where(Activity.actor_id == absorb_id).values(actor_id=keep_id)
    )

    # Transfer notifications
    await db.execute(
        update(Notification)
        .where(Notification.person_id == absorb_id)
        .values(person_id=keep_id)
    )

    # Transfer absences (both as person and as substitute)
    await db.execute(
        update(Absence).where(Absence.person_id == absorb_id).values(person_id=keep_id)
    )
    await db.execute(
        update(Absence)
        .where(Absence.substitute_id == absorb_id)
        .values(substitute_id=keep_id)
    )

    # Delete the absorbed person
    await db.delete(absorb)
    await db.flush()

    # Re-fetch keep with eager loading
    stmt = (
        select(Person)
        .where(Person.id == keep_id)
        .options(selectinload(Person.emails), selectinload(Person.phones))
    )
    result = await db.execute(stmt)
    return result.scalar_one()
