"""Which organisatie-eenheden a resource belongs to.

Kept for ``core.authority``: the answer comes from the one locator in
``core.authz`` (``get_eenheid_ids``).  For an initiatief that is only the
eenheden linked as eigenaar; for an opdracht its opdrachtgever and
opdrachtnemer-eenheid.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


async def get_authority_eenheid_ids(
    db: AsyncSession,
    resource_type: str,
    resource_id: UUID,
) -> tuple[bool, list[UUID]]:
    """Return ``(found, eenheid_ids)`` for deciding authority over a resource.

    Rights on any of the returned eenheden (or above them) count.  An empty
    list means the resource has no eenheid: only its own eigenaars decide.
    """
    from bouwmeester.core.authz import get_eenheid_ids

    return await get_eenheid_ids(db, resource_type, resource_id)
