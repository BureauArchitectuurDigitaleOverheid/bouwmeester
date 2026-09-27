"""Who sees which initiatieven and leads: one definition for lists and details.

An initiatief is visible to a person when

- a system role grants ``initiatief:read`` (super_admin), or
- they hold a resource role on it, directly or through an eenheid they are
  placed in (every initiatief role includes ``initiatief:read``), or
- an eenheid that owns it (linked as ``eigenaar``) is visible to them in the
  org chart (``core.org_context``, the same visible set): their own eenheden
  and those above their own internal ones (members of the organisation read
  up its line), plus the subtrees they manage or may write in.

The last rule is the org visibility of nodes, applied to the owning eenheid,
so nodes and initiatieven follow one rule.  It covers everyone who may write
an initiatief through a role on an eenheid (``core.authz`` step 4 needs a
write permission on the owning eenheid or above it, and such eenheden make
their subtree visible).  Plain members of an eenheid above the owner do not
read down: they only see that far through a role that lets them write.

A lead is visible when its initiatief is visible, when the person holds a
resource role on the lead itself (opdrachtgever, contactpersoon,
betrokken; directly or through an eenheid), or when it has no initiatief
and its eenheid is visible in the org chart.  Only a lead with neither an
initiatief nor an eenheid is tenant-wide (leads from before initiatieven
existed).

Lists filter with ``apply_initiatief_filter`` / ``apply_lead_filter``;
single items ask ``core.authz`` (``initiatief:read`` / ``lead:read``),
which answers from the same context, so a list and a detail can never
disagree.  Writes are decided by ``core.authz`` too.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from fastapi import Depends
from sqlalchemy import and_, false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import get_db
from bouwmeester.core.org_context import (
    OrgContext,
    build_org_context,
    org_eenheid_clause,
    sees_eenheid,
)
from bouwmeester.core.permissions import PermissionContext, get_permission_context
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.lead import Lead
from bouwmeester.models.person import Person
from bouwmeester.models.resource_permission import ResourcePermission

logger = logging.getLogger(__name__)


@dataclass
class InitiatiefContext:
    """The initiatieven and lead roles visible to the current user."""

    person_id: UUID | None = None
    visible_initiatief_ids: list[UUID] = field(default_factory=list)
    # The caller's org visibility, for leads without initiatief.
    org_ctx: OrgContext | None = None
    # Leads the person holds a resource role on (seen regardless of initiatief).
    lead_role_ids: list[UUID] = field(default_factory=list)
    is_admin: bool = False
    is_authenticated: bool = False

    def sees_initiatief(self, initiatief_id: UUID) -> bool:
        if self.is_admin:
            return True
        return self.is_authenticated and initiatief_id in self.visible_initiatief_ids

    def sees_lead(self, lead: Lead) -> bool:
        return self.sees_lead_in(
            lead.id, lead.initiatief_id, lead.organisatie_eenheid_id
        )

    def sees_lead_in(
        self, lead_id: UUID, initiatief_id: UUID | None, eenheid_id: UUID | None
    ) -> bool:
        """``sees_lead`` for a lead known by its id, initiatief and eenheid."""
        if self.is_admin:
            return True
        if not self.is_authenticated:
            return False
        if lead_id in self.lead_role_ids:
            return True
        if initiatief_id is not None:
            return initiatief_id in self.visible_initiatief_ids
        return eenheid_id is None or (
            self.org_ctx is not None and sees_eenheid(self.org_ctx, eenheid_id)
        )


def _role_holder_clause(person_id: UUID, own_eenheid_ids: list[UUID]):
    """A resource role held by the person, directly or via a placement."""
    return or_(
        ResourcePermission.person_id == person_id,
        ResourcePermission.organisatie_eenheid_id.in_(own_eenheid_ids),
    )


async def build_initiatief_context(
    db: AsyncSession,
    person: Person | None,
    *,
    perm_ctx: PermissionContext | None = None,
    org_ctx: OrgContext | None = None,
) -> InitiatiefContext:
    """Build an InitiatiefContext for the given person.

    Pass the caller's *perm_ctx* and *org_ctx* to avoid building them again.
    """
    from bouwmeester.core.permissions import (
        anonymous_permission_context,
        build_permission_context,
    )

    if person is None:
        # Dev mode sees everything; otherwise an anonymous request sees nothing.
        anon = perm_ctx or anonymous_permission_context()
        return InitiatiefContext(
            is_admin=anon.is_super_admin, is_authenticated=anon.is_authenticated
        )
    if perm_ctx is None:
        perm_ctx = await build_permission_context(db, person)
    if perm_ctx.has_system_permission("initiatief:read"):
        return InitiatiefContext(
            person_id=person.id, is_admin=True, is_authenticated=True
        )
    if org_ctx is None:
        org_ctx = await build_org_context(db, person, perm_ctx=perm_ctx)

    own = list(org_ctx.own_eenheid_ids)
    initiatief_ids = await db.scalars(
        select(ResourcePermission.resource_id)
        .where(
            ResourcePermission.resource_type == "initiatief",
            or_(
                _role_holder_clause(person.id, own),
                and_(
                    ResourcePermission.rol == "eigenaar",
                    ResourcePermission.organisatie_eenheid_id.in_(
                        org_ctx.visible_eenheid_ids
                    ),
                ),
            ),
        )
        .distinct()
    )
    lead_ids = await db.scalars(
        select(ResourcePermission.resource_id)
        .where(
            ResourcePermission.resource_type == "lead",
            _role_holder_clause(person.id, own),
        )
        .distinct()
    )
    return InitiatiefContext(
        person_id=person.id,
        visible_initiatief_ids=list(initiatief_ids.all()),
        org_ctx=org_ctx,
        lead_role_ids=list(lead_ids.all()),
        is_admin=False,
        is_authenticated=True,
    )


async def get_initiatief_context(
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> InitiatiefContext:
    """FastAPI dependency: the caller's InitiatiefContext (built once, in authz)."""
    from bouwmeester.core.authz import visibility

    _, init_ctx = await visibility(db, perm_ctx)
    return init_ctx


def apply_initiatief_filter(stmt, ctx: InitiatiefContext | None):
    """Restrict a select over ``Initiatief`` to the visible initiatieven."""
    if ctx is None or ctx.is_admin:
        return stmt
    if not ctx.is_authenticated:
        return stmt.where(false())
    return stmt.where(Initiatief.id.in_(ctx.visible_initiatief_ids))


def apply_lead_filter(stmt, ctx: InitiatiefContext | None):
    """Restrict a select over ``Lead`` to the visible leads (see ``sees_lead``)."""
    if ctx is None or ctx.is_admin:
        return stmt
    if not ctx.is_authenticated:
        return stmt.where(false())
    eenheid_visible = (
        org_eenheid_clause(Lead.organisatie_eenheid_id, ctx.org_ctx)
        if ctx.org_ctx is not None
        else Lead.organisatie_eenheid_id.is_(None)
    )
    return stmt.where(
        or_(
            and_(Lead.initiatief_id.is_(None), eenheid_visible),
            Lead.initiatief_id.in_(ctx.visible_initiatief_ids),
            Lead.id.in_(ctx.lead_role_ids),
        )
    )
