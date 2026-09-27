"""Who may instruct an agent: only super_admin (product decision).

An agent acts on what it is handed with its own rights, not the sender's,
so handing it work lets the sender borrow those rights.  A DM or reply, a
task or lead assigned to it, an @mention, a role, a grant or a placement
all hand it work or power; every path asks the one rule here.

Work the system generates (worker jobs, follow-up tasks, notifications
without a sender) comes from ``SYSTEM_ACTOR``, which is no super_admin: the
system never instructs an agent, so whoever triggers it cannot either.
"""

from uuid import UUID

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.permissions import PermissionContext
from bouwmeester.models.person import Person

AGENT_INSTRUCTION_REFUSED = "Alleen systeembeheerders mogen een agent aansturen"

# The system as actor: authenticated, but no super_admin.
SYSTEM_ACTOR = PermissionContext(is_authenticated=True)


def may_instruct(perm_ctx: PermissionContext, target: Person | None) -> bool:
    """May the caller hand *target* work?  Anyone but an agent: yes."""
    return target is None or not target.is_agent or perm_ctx.is_super_admin


async def sender_may_instruct(
    db: AsyncSession, sender_id: UUID | None, target: Person | None
) -> bool:
    """:func:`may_instruct` for a sender known by id; None is the system."""
    if target is None or not target.is_agent:
        return True
    if sender_id is None:
        return may_instruct(SYSTEM_ACTOR, target)
    from bouwmeester.core.authz import perm_ctx_for

    return may_instruct(await perm_ctx_for(db, sender_id), target)


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
