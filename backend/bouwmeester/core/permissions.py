"""Permission engine — central RBAC + resource permission resolution.

Mirrors the pattern of org_context.py: builds a PermissionContext per
request, cached on request.state, and provides FastAPI dependencies
for permission checking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import get_optional_user
from bouwmeester.core.database import get_db
from bouwmeester.models.person import Person
from bouwmeester.repositories.resource_permission import ResourcePermissionRepository
from bouwmeester.repositories.role import PersonRoleRepository, RoleRepository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resource role -> permission mappings (fixed business rules)
# ---------------------------------------------------------------------------

RESOURCE_ROLE_PERMISSIONS: dict[str, dict[str, set[str]]] = {
    "corpus_node": {
        "eigenaar": {
            "node:read",
            "node:update",
            "node:delete",
            "resource_permission:manage",
        },
        "betrokken": {"node:read", "node:update"},
        "adviseur": {"node:read"},
        "indiener": {"node:read"},
    },
    "initiatief": {
        "eigenaar": {
            "initiatief:read",
            "initiatief:update",
            "initiatief:delete",
            "resource_permission:manage",
        },
        "contributor": {"initiatief:read", "initiatief:update"},
        "viewer": {"initiatief:read"},
    },
    "lead": {
        "opdrachtgever": {"lead:read", "lead:update"},
        "contactpersoon": {"lead:read"},
        "betrokken": {"lead:read"},
    },
    "opdracht": {
        "eigenaar": {
            "opdracht:read",
            "opdracht:update",
            "opdracht:delete",
            "resource_permission:manage",
        },
        "betrokken": {"opdracht:read"},
    },
}


@dataclass
class PermissionContext:
    """Resolved permissions for the current user, cached per-request."""

    person_id: UUID | None = None
    is_authenticated: bool = False
    system_roles: list[str] = field(default_factory=list)
    scoped_roles: dict[UUID, list[str]] = field(default_factory=dict)
    effective_permissions: set[str] = field(default_factory=set)
    # Permissions granted only by system-level roles (apply to all eenheden)
    system_permissions: set[str] = field(default_factory=set)
    # Per-eenheid resolved permissions for scoped checks
    scoped_permissions: dict[UUID, set[str]] = field(default_factory=dict)
    is_super_admin: bool = False

    def has_permission(self, perm: str) -> bool:
        """Check if the user has a permission (any scope)."""
        if self.is_super_admin:
            return True
        return perm in self.effective_permissions

    def has_permission_for_eenheid(self, perm: str, eenheid_id: UUID) -> bool:
        """Check if the user has a permission for a specific eenheid."""
        if self.is_super_admin:
            return True
        # System-level permissions apply everywhere
        if perm in self.system_permissions:
            return True
        # Check scoped permissions for this specific eenheid
        eenheid_perms = self.scoped_permissions.get(eenheid_id, set())
        return perm in eenheid_perms

    def has_any_permission(self, *perms: str) -> bool:
        if self.is_super_admin:
            return True
        return bool(self.effective_permissions & set(perms))


async def build_permission_context(
    db: AsyncSession,
    person: Person,
) -> PermissionContext:
    """Build a PermissionContext by querying person_role + role_permission.

    Members of an eenheid (via PersonOrganisatieEenheid) who have no
    explicit PersonRole on that eenheid receive an implicit ``viewer``
    role so they can see modules enabled for their team.
    """
    pr_repo = PersonRoleRepository(db)
    system_roles, scoped_roles = await pr_repo.get_active_role_ids_for_person(person.id)

    is_super_admin = "super_admin" in system_roles

    if is_super_admin:
        # Resolve all permissions so they can be enumerated
        role_repo = RoleRepository(db)
        all_perms = await role_repo.get_role_permission_ids("super_admin")
        return PermissionContext(
            person_id=person.id,
            is_authenticated=True,
            system_roles=system_roles,
            scoped_roles=scoped_roles,
            effective_permissions=all_perms,
            system_permissions=all_perms,
            is_super_admin=True,
        )

    # Grant implicit viewer role for eenheden the person is a member of
    # but has no explicit PersonRole on.
    from bouwmeester.core.org_context import _get_own_eenheid_ids

    member_eenheid_ids = await _get_own_eenheid_ids(db, person.id)
    for eid in member_eenheid_ids:
        if eid not in scoped_roles:
            scoped_roles[eid] = ["viewer"]

    # Resolve per-role permissions
    role_repo = RoleRepository(db)

    # Collect all unique role IDs for a single batch query
    all_role_ids = list(set(system_roles))
    for role_ids in scoped_roles.values():
        all_role_ids.extend(role_ids)
    all_role_ids = list(set(all_role_ids))

    # Get per-role permission sets
    role_perm_cache: dict[str, set[str]] = {}
    for role_id in all_role_ids:
        role_perm_cache[role_id] = await role_repo.get_role_permission_ids(role_id)

    # Build per-eenheid permissions
    scoped_permissions: dict[UUID, set[str]] = {}
    for eenheid_id, role_ids in scoped_roles.items():
        eenheid_perms: set[str] = set()
        for role_id in role_ids:
            eenheid_perms |= role_perm_cache.get(role_id, set())
        scoped_permissions[eenheid_id] = eenheid_perms

    # Subtract disabled modules per eenheid
    if scoped_permissions:
        from bouwmeester.repositories.eenheid_module import (
            EenheidModuleRepository,
        )
        from bouwmeester.schema.eenheid_module import (
            MODULE_PERMISSION_CATEGORIES,
        )

        em_repo = EenheidModuleRepository(db)
        disabled_map = await em_repo.get_all_disabled_modules_bulk(
            list(scoped_permissions.keys())
        )
        has_any_disabled = any(disabled_map.values())

        if has_any_disabled:
            # Build category → permission-id mapping (one query, reused)
            from bouwmeester.models.role import Permission as PermModel

            cat_stmt = select(PermModel.id, PermModel.category)
            cat_result = await db.execute(cat_stmt)
            perm_by_category: dict[str, set[str]] = {}
            for pid, cat in cat_result.all():
                perm_by_category.setdefault(cat, set()).add(pid)

            for eenheid_id, disabled_modules in disabled_map.items():
                if not disabled_modules:
                    continue
                denied_perms: set[str] = set()
                for mod in disabled_modules:
                    for cat in MODULE_PERMISSION_CATEGORIES.get(mod, []):
                        denied_perms |= perm_by_category.get(cat, set())
                scoped_permissions[eenheid_id] -= denied_perms

    # System-level permissions (apply to all eenheden)
    system_perms: set[str] = set()
    for role_id in system_roles:
        system_perms |= role_perm_cache.get(role_id, set())

    # Effective = union of system + all scoped
    effective_permissions: set[str] = set(system_perms)
    for perms in scoped_permissions.values():
        effective_permissions |= perms

    return PermissionContext(
        person_id=person.id,
        is_authenticated=True,
        system_roles=system_roles,
        scoped_roles=scoped_roles,
        effective_permissions=effective_permissions,
        system_permissions=system_perms,
        scoped_permissions=scoped_permissions,
        is_super_admin=False,
    )


async def get_permission_context(
    request: Request,
    person: Person | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> PermissionContext:
    """FastAPI dependency returning the PermissionContext for the current user.

    Cached on request.state to avoid re-computation.
    """
    cached = getattr(request.state, "permission_context", None)
    if cached is not None:
        return cached

    if person is None:
        from bouwmeester.core.config import get_settings

        settings = get_settings()
        if not settings.OIDC_ISSUER:
            # Dev mode: treat as super_admin
            ctx = PermissionContext(is_authenticated=True, is_super_admin=True)
        else:
            ctx = PermissionContext(is_authenticated=False)
    else:
        ctx = await build_permission_context(db, person)

    request.state.permission_context = ctx
    return ctx


async def check_resource_permission(
    db: AsyncSession,
    person_id: UUID,
    resource_type: str,
    resource_id: UUID,
    required_perm: str,
) -> bool:
    """Check if a person has a resource-level permission."""
    rp_repo = ResourcePermissionRepository(db)
    roles = await rp_repo.get_roles_for_person_resource(
        person_id, resource_type, resource_id
    )
    type_mappings = RESOURCE_ROLE_PERMISSIONS.get(resource_type, {})
    for rol in roles:
        granted = type_mappings.get(rol, set())
        if required_perm in granted:
            return True
    return False


def require_permission(*perms: str):
    """Dependency factory: raises 403 if the user lacks ALL listed permissions.

    Usage::

        @router.get("/")
        async def my_endpoint(
            _perm=Depends(require_permission("node:create")),
        ):
            ...
    """

    async def _check(
        perm_ctx: PermissionContext = Depends(get_permission_context),
    ) -> PermissionContext:
        if not perm_ctx.is_authenticated:
            raise HTTPException(status_code=401, detail="Not authenticated")
        if perm_ctx.is_super_admin:
            return perm_ctx
        if not perm_ctx.has_any_permission(*perms):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return perm_ctx

    return _check


def require_any_permission(*perms: str):
    """Alias for require_permission (OR logic)."""
    return require_permission(*perms)
