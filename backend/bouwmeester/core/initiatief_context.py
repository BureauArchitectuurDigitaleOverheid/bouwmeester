"""Who sees which initiatieven and leads: one definition for lists and details.

An initiatief is visible to a person when

- a system role grants ``initiatief:read`` (super_admin), or
- they hold a resource role on it, directly or through an eenheid they are
  placed in (every initiatief role includes ``initiatief:read``), or
- an eenheid that owns it (linked as ``eigenaar``) is visible to them in the
  org chart (``core.org_context``): their own eenheden and those above them
  (members read up the line), plus the subtrees they manage or may write in.

The last rule is the org visibility of nodes, applied to the owning eenheid,
so nodes and initiatieven follow one rule.  It covers everyone who may write
an initiatief through a role on an eenheid (``core.authz`` step 4 needs a
write permission on the owning eenheid or above it, and such eenheden make
their subtree visible).  Plain members of an eenheid above the owner do not
read down: they only see that far through a role that lets them write.

A lead is visible when it has no initiatief (tenant-wide during the
migration period), when its initiatief is visible, or when the person holds
a resource role on the lead itself (opdrachtgever, contactpersoon,
betrokken), directly or through an eenheid.

Lists filter with ``apply_initiatief_filter`` / ``apply_lead_filter``;
single items ask ``sees_initiatief`` / ``sees_lead`` on the same context,
so a list and a detail can never disagree.  Writes are decided by
``core.authz``; the access level shown in the frontend combines the two.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import and_, false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import get_optional_user
from bouwmeester.core.authz import can
from bouwmeester.core.database import get_db
from bouwmeester.core.org_context import (
    OrgContext,
    build_org_context,
    get_org_context,
)
from bouwmeester.core.permissions import PermissionContext, get_permission_context
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.lead import Lead
from bouwmeester.models.person import Person
from bouwmeester.models.resource_permission import ResourcePermission

logger = logging.getLogger(__name__)

# The write levels the frontend shows, strongest first, and the permission
# that earns them.  Below these, a visible initiatief is ``viewer``.
ACCESS_LEVEL_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("eigenaar", "initiatief:delete"),
    ("contributor", "initiatief:update"),
)


@dataclass
class InitiatiefContext:
    """The initiatieven and lead roles visible to the current user."""

    person_id: UUID | None = None
    visible_initiatief_ids: list[UUID] = field(default_factory=list)
    # Leads the person holds a resource role on (seen regardless of initiatief).
    lead_role_ids: list[UUID] = field(default_factory=list)
    is_admin: bool = False
    is_authenticated: bool = False

    def sees_initiatief(self, initiatief_id: UUID) -> bool:
        if self.is_admin:
            return True
        return self.is_authenticated and initiatief_id in self.visible_initiatief_ids

    def sees_lead(self, lead: Lead) -> bool:
        if self.is_admin:
            return True
        return self.is_authenticated and (
            lead.initiatief_id is None
            or lead.initiatief_id in self.visible_initiatief_ids
            or lead.id in self.lead_role_ids
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
        lead_role_ids=list(lead_ids.all()),
        is_admin=False,
        is_authenticated=True,
    )


async def get_initiatief_context(
    request: Request,
    person: Person | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
    org_ctx: OrgContext = Depends(get_org_context),
) -> InitiatiefContext:
    """FastAPI dependency that returns the InitiatiefContext."""
    cached = getattr(request.state, "initiatief_context", None)
    if cached is not None:
        return cached

    ctx = await build_initiatief_context(db, person, perm_ctx=perm_ctx, org_ctx=org_ctx)

    request.state.initiatief_context = ctx
    return ctx


async def _context_for(
    db: AsyncSession, perm_ctx: PermissionContext
) -> InitiatiefContext:
    """The context for callers that only hold a PermissionContext."""
    person = await db.get(Person, perm_ctx.person_id) if perm_ctx.person_id else None
    return await build_initiatief_context(db, person, perm_ctx=perm_ctx)


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
    return stmt.where(
        or_(
            Lead.initiatief_id.is_(None),
            Lead.initiatief_id.in_(ctx.visible_initiatief_ids),
            Lead.id.in_(ctx.lead_role_ids),
        )
    )


async def require_initiatief_read(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    initiatief_id: UUID,
    init_ctx: InitiatiefContext | None = None,
) -> None:
    """404 unless the caller sees this initiatief.

    404 rather than 403: that an initiatief exists is information too.
    """
    ctx = init_ctx or await _context_for(db, perm_ctx)
    if not ctx.sees_initiatief(initiatief_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Initiatief niet gevonden")


async def require_lead_read(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    lead_id: UUID,
    init_ctx: InitiatiefContext | None = None,
) -> Lead:
    """The lead, or 404 unless the caller sees it."""
    lead = await db.get(Lead, lead_id)
    ctx = init_ctx or await _context_for(db, perm_ctx)
    if lead is None or not ctx.sees_lead(lead):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead niet gevonden")
    return lead


async def initiatief_access_level(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    initiatief_id: UUID,
    init_ctx: InitiatiefContext | None = None,
) -> str | None:
    """The caller's access level: a write level from ``authz.can``, else viewer."""
    for level, permission in ACCESS_LEVEL_PERMISSIONS:
        if await can(db, perm_ctx, permission, "initiatief", initiatief_id):
            return level
    ctx = init_ctx or await _context_for(db, perm_ctx)
    return "viewer" if ctx.sees_initiatief(initiatief_id) else None
