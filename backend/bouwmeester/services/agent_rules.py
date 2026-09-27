"""Who may instruct an agent: only super_admin (product decision).

An agent acts on what it is handed with its own rights, not the sender's,
so handing it work lets the sender borrow those rights.  A DM or reply, a
task or lead assigned to it, and an @mention all hand it work; every path
asks the one rule here.
"""

from uuid import UUID

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.permissions import PermissionContext
from bouwmeester.models.person import Person

AGENT_INSTRUCTION_REFUSED = "Alleen systeembeheerders mogen een agent aansturen"


def may_instruct(perm_ctx: PermissionContext, target: Person | None) -> bool:
    """May the caller hand *target* work?  Anyone but an agent: yes."""
    return target is None or not target.is_agent or perm_ctx.is_super_admin


def require_may_instruct(perm_ctx: PermissionContext, target: Person | None) -> None:
    """:func:`may_instruct`, or 403."""
    if not may_instruct(perm_ctx, target):
        raise HTTPException(status.HTTP_403_FORBIDDEN, AGENT_INSTRUCTION_REFUSED)


async def require_may_assign(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    data: BaseModel,
    *,
    current: UUID | None = None,
    field: str = "assignee_id",
) -> None:
    """May the caller set the person in *field* of body *data*?  Raises 403 if not.

    The assignee of a task or a lead, or the verantwoordelijke of an opdracht
    (who gets the opdracht's follow-up tasks), created or updated.  Only a
    change is an instruction: sending the person already set (*current*) is not.
    """
    if field not in data.model_fields_set:
        return
    person_id = getattr(data, field)
    if person_id is None or person_id == current:
        return
    require_may_instruct(perm_ctx, await db.get(Person, person_id))
