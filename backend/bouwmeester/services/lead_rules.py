"""The rules for where a new lead goes and whether the caller may put it there.

One place for ``POST /leads`` and the chat's ``create_lead`` tool, so they
cannot drift apart.  ``core.authz.can_anywhere("lead:create", "lead")``
answers the same question for a create button.  Also the rule for what a
lead puts on the public page of its initiatief (``require_may_publish``).
"""

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.authz import can, own_eenheid_where, require
from bouwmeester.core.permissions import PermissionContext
from bouwmeester.models.lead_column import LeadColumn
from bouwmeester.schema.lead import LeadCreate
from bouwmeester.services.agent_rules import require_may_assign

NO_EENHEID_FOR_LEAD = (
    "Kies een initiatief of eenheid voor de lead: je mag in geen van je eigen "
    "organisatie-eenheden leads aanmaken."
)

MAY_NOT_PUBLISH = (
    "Wat een lead op de publieke pagina van het initiatief zet, beslist wie "
    "het initiatief mag bewerken."
)

# The fields of a lead the public page of its initiatief shows, with their
# value on a new lead.
PUBLIC_LEAD_FIELDS: dict[str, Any] = {
    "public_visible": False,
    "public_title": None,
    "public_summary": None,
}


async def require_may_publish(
    db: AsyncSession, perm_ctx: PermissionContext, initiatief_id: UUID | None
) -> None:
    """Guard putting lead content on the initiatief's public page; 403.

    The public page is the initiatief's (its eigenaar switches it on), so
    what a lead shows there, its public fields and its published posts with
    a public text, is ``initiatief:update`` on that initiatief.
    ``lead:update`` alone (an opdrachtgever on the lead) does not reach it.
    A lead without initiatief shows on no page.
    """
    if initiatief_id is not None and not await can(
        db, perm_ctx, "initiatief:update", "initiatief", initiatief_id
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, MAY_NOT_PUBLISH)


async def require_may_publish_lead(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    changes: dict[str, Any],
    before: Any = None,
) -> None:
    """``require_may_publish`` for a new lead or a change to one.

    *changes* holds the fields sent, *before* the lead as it is (None for a
    new one).  Asked when a public field changes, when a lead that is on
    the public page moves to another initiatief (it lands on that page), or
    when a lead with public fields moves into or out of a public column
    (``LeadColumn.is_public_visible``): that puts it on or takes it off
    the page.
    """
    now = {
        field: getattr(before, field) if before is not None else default
        for field, default in PUBLIC_LEAD_FIELDS.items()
    }
    changed = any(f in changes and changes[f] != now[f] for f in now)
    old_initiatief = before.initiatief_id if before is not None else None
    initiatief_id = changes.get("initiatief_id", old_initiatief)
    moved = before is not None and initiatief_id != old_initiatief
    public = changes.get("public_visible", now["public_visible"])
    if changed or (moved and public):
        await require_may_publish(db, perm_ctx, initiatief_id)
    elif (
        public
        and before is not None
        and changes.get("stage", before.stage) != before.stage
        and await _public_stage(db, initiatief_id, before.stage)
        != await _public_stage(db, initiatief_id, changes["stage"])
    ):
        await require_may_publish(db, perm_ctx, initiatief_id)


async def _public_stage(
    db: AsyncSession, initiatief_id: UUID | None, stage: str | None
) -> bool:
    """Does the public page of *initiatief_id* show leads in *stage*?"""
    if initiatief_id is None or stage is None:
        return False
    return bool(
        await db.scalar(
            select(LeadColumn.id).where(
                LeadColumn.initiatief_id == initiatief_id,
                LeadColumn.slug == stage,
                LeadColumn.is_public_visible.is_(True),
            )
        )
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
    nowhere in particular (tenant-wide).  Its assignee must be one the
    caller may hand work (``agent_rules``).
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
    await require_may_publish_lead(db, perm_ctx, data.model_dump(exclude_unset=True))
    await require_may_assign(db, perm_ctx, data)
