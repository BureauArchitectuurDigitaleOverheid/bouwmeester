"""Which organisatie-eenheid a resource belongs to.

Two questions, answered from the database:

- ``resolve_resource_eenheid_id``: the eenheid used for *visibility*
  (``org_context.check_resource_org_scope``).
- ``get_authority_eenheid_ids``: the eenheden whose rights give *authority*
  over the resource (``core.authority``).  For an initiatief that is only the
  eenheden linked as eigenaar, never an eenheid that merely has read access,
  and the answer does not depend on row order.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.resource_permission import ResourcePermission


async def _initiatief_owner_eenheid_ids(
    db: AsyncSession, initiatief_id: UUID
) -> list[UUID]:
    result = await db.execute(
        select(ResourcePermission.organisatie_eenheid_id).where(
            ResourcePermission.resource_type == "initiatief",
            ResourcePermission.resource_id == initiatief_id,
            ResourcePermission.rol == "eigenaar",
            ResourcePermission.organisatie_eenheid_id.isnot(None),
        )
    )
    return list(result.scalars().all())


async def get_authority_eenheid_ids(
    db: AsyncSession,
    resource_type: str,
    resource_id: UUID,
) -> tuple[bool, list[UUID]]:
    """Return ``(found, eenheid_ids)`` for deciding authority over a resource.

    Rights on any of the returned eenheden (or above them) count.  An empty
    list means the resource has no eenheid: only its own eigenaars decide.
    """
    if resource_type == "initiatief":
        from bouwmeester.models.initiatief import Initiatief

        if await db.get(Initiatief, resource_id) is None:
            return False, []
        return True, await _initiatief_owner_eenheid_ids(db, resource_id)

    if resource_type == "lead":
        from bouwmeester.models.lead import Lead

        lead = await db.get(Lead, resource_id)
        if lead is None:
            return False, []
        if lead.initiatief_id is not None:
            return True, await _initiatief_owner_eenheid_ids(db, lead.initiatief_id)
        return True, [
            lead.organisatie_eenheid_id
        ] if lead.organisatie_eenheid_id else []

    if resource_type == "opdracht":
        from bouwmeester.models.opdracht import Opdracht

        opdracht = await db.get(Opdracht, resource_id)
        if opdracht is None:
            return False, []
        # The client and the team doing the work both answer for it.
        owners = [opdracht.opdrachtgever_id, opdracht.opdrachtnemer_eenheid_id]
        return True, [eid for eid in owners if eid is not None]

    found, eenheid_id = await resolve_resource_eenheid_id(
        db, resource_type, resource_id
    )
    return found, [eenheid_id] if eenheid_id else []


async def resolve_resource_eenheid_id(
    db: AsyncSession,
    resource_type: str,
    resource_id: UUID,
) -> tuple[bool, UUID | None]:
    """Resolve the organisatie_eenheid_id for a polymorphic resource.

    Returns ``(found, eenheid_id)`` — *found* is ``False`` when the
    resource does not exist (distinguishing from a resource that exists
    but has no eenheid assigned).
    """
    if resource_type == "corpus_node":
        from bouwmeester.models.corpus_node import CorpusNode

        stmt = select(CorpusNode.organisatie_eenheid_id).where(
            CorpusNode.id == resource_id
        )
        result = await db.execute(stmt)
        row = result.one_or_none()
        return (True, row[0]) if row is not None else (False, None)

    if resource_type == "organisatie_eenheid":
        from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid

        stmt = select(OrganisatieEenheid.id).where(OrganisatieEenheid.id == resource_id)
        result = await db.execute(stmt)
        row = result.one_or_none()
        return (True, row[0]) if row is not None else (False, None)

    if resource_type == "opdracht":
        from bouwmeester.models.opdracht import Opdracht

        stmt = select(Opdracht.opdrachtgever_id).where(Opdracht.id == resource_id)
        result = await db.execute(stmt)
        row = result.one_or_none()
        return (True, row[0]) if row is not None else (False, None)

    if resource_type == "task":
        from bouwmeester.models.task import Task

        stmt = select(Task.organisatie_eenheid_id).where(Task.id == resource_id)
        result = await db.execute(stmt)
        row = result.one_or_none()
        return (True, row[0]) if row is not None else (False, None)

    if resource_type == "initiatief":
        stmt = select(ResourcePermission.organisatie_eenheid_id).where(
            ResourcePermission.resource_type == "initiatief",
            ResourcePermission.resource_id == resource_id,
            ResourcePermission.organisatie_eenheid_id.isnot(None),
        )
        result = await db.execute(stmt)
        first = result.scalars().first()
        return (True, first)

    if resource_type == "lead":
        from bouwmeester.models.lead import Lead

        stmt = (
            select(ResourcePermission.organisatie_eenheid_id)
            .join(Lead, Lead.initiatief_id == ResourcePermission.resource_id)
            .where(
                Lead.id == resource_id,
                ResourcePermission.resource_type == "initiatief",
                ResourcePermission.organisatie_eenheid_id.isnot(None),
            )
        )
        result = await db.execute(stmt)
        first = result.scalars().first()
        return (True, first)

    return (False, None)
