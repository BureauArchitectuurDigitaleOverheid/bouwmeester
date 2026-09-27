"""The rule for where a new lead goes and whether the caller may put it there.

One place for ``POST /leads`` and the chat's ``create_lead`` tool, so they
cannot drift apart.  ``core.authz.can_anywhere("lead:create", "lead")``
answers the same question for a create button.
"""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.authz import own_eenheid_where, require
from bouwmeester.core.permissions import PermissionContext
from bouwmeester.schema.lead import LeadCreate

NO_EENHEID_FOR_LEAD = (
    "Kies een initiatief of eenheid voor de lead: je mag in geen van je eigen "
    "organisatie-eenheden leads aanmaken."
)


async def require_lead_create(
    db: AsyncSession, perm_ctx: PermissionContext, data: LeadCreate
) -> None:
    """Place a new lead and guard creating it there; raises like ``require``.

    A lead in an initiatief or an eenheid is decided there.  Without either
    it lands in the caller's own eenheid (``own_eenheid_where``: the
    longest-running trusted placement where ``lead:create`` holds), filled
    into *data*.
    Without such an eenheid only system roles create a lead that lives
    nowhere in particular (tenant-wide).
    """
    if (
        perm_ctx.is_authenticated
        and data.initiatief_id is None
        and data.organisatie_eenheid_id is None
    ):
        own = await own_eenheid_where(db, perm_ctx, "lead:create", "lead")
        if own is not None:
            data.organisatie_eenheid_id = own
        elif not perm_ctx.has_system_permission("lead:create"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, NO_EENHEID_FOR_LEAD)
    await require(db, perm_ctx, "lead:create", "lead", place=data)
