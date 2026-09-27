"""Who a service acts for when there is no request dependency to ask.

The chat and Mattermost slash commands run tools for a person id.  They
resolve that person here, through ``core.authz`` (``perm_ctx_for`` and
``visibility``), the same way the REST dependencies do.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.authz import perm_ctx_for, visibility
from bouwmeester.core.initiatief_context import InitiatiefContext
from bouwmeester.core.org_context import OrgContext
from bouwmeester.core.permissions import PermissionContext
from bouwmeester.core.whitelist import is_email_allowed
from bouwmeester.models.person import Person
from bouwmeester.repositories.mattermost_user import MattermostUserRepository


@dataclass(frozen=True)
class Caller:
    """Rights and visibility of the person a service acts for."""

    person_id: UUID | None
    perm_ctx: PermissionContext
    org_ctx: OrgContext
    init_ctx: InitiatiefContext


def may_still_act(person: Person | None) -> bool:
    """May a person reached outside a login still act?

    A Mattermost account link (slash commands, reactions, DMs, the posts it
    authors) stands in for a login, so it gets what ``AuthRequiredMiddleware``
    asks of one: the person is active and on the access whitelist.  The
    whitelist is checked against ``oidc_email``, the address of the last
    login, which the API cannot edit; a person who never logged in has none
    and is refused while the whitelist is active.
    """
    return (
        person is not None
        and person.is_active
        and is_email_allowed(person.oidc_email or "")
    )


async def linked_person_id(db: AsyncSession, mattermost_user_id: str) -> UUID | None:
    """The person behind a Mattermost account, when they may still act."""
    mapping = await MattermostUserRepository(db).get_by_mattermost_user_id(
        mattermost_user_id
    )
    if mapping is None:
        return None
    person = await db.get(Person, mapping.person_id)
    return person.id if may_still_act(person) else None


async def caller_for(db: AsyncSession, person_id: UUID | None) -> Caller:
    """The caller behind *person_id*, resolved once per database session.

    ``None`` or an unknown id is anonymous, like the REST dependencies (in
    dev mode that sees everything).  The permission context is kept in
    ``db.info``; visibility is cached on it by ``core.authz``.
    """
    key = ("caller_perm_ctx", person_id)
    perm_ctx = db.info.get(key)
    if perm_ctx is None:
        perm_ctx = db.info[key] = await perm_ctx_for(db, person_id)
    org_ctx, init_ctx = await visibility(db, perm_ctx)
    return Caller(person_id, perm_ctx, org_ctx, init_ctx)
