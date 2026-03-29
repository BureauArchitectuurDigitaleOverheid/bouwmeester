"""Role management API routes."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import (
    build_permission_context,
    require_permission,
)
from bouwmeester.models.person import Person
from bouwmeester.repositories.role import (
    PersonRoleRepository,
    RoleRepository,
)
from bouwmeester.schema.role import (
    MyPermissionsResponse,
    PersonRoleCreate,
    PersonRoleResponse,
    RoleWithPermissionsResponse,
)
from bouwmeester.services.activity_service import log_activity

router = APIRouter(prefix="/roles", tags=["roles"])


def _assignment_to_response(a) -> PersonRoleResponse:
    return PersonRoleResponse(
        id=a.id,
        person_id=a.person_id,
        person_naam=(a.person.naam if a.person else None),
        role_id=a.role_id,
        role_naam=a.role.naam if a.role else None,
        organisatie_eenheid_id=a.organisatie_eenheid_id,
        organisatie_eenheid_naam=(
            a.organisatie_eenheid.naam if a.organisatie_eenheid else None
        ),
        granted_by_id=a.granted_by_id,
        start_datum=a.start_datum,
        eind_datum=a.eind_datum,
        created_at=a.created_at,
    )


async def _get_max_rank(perm, role_repo: RoleRepository) -> int:
    """Get the highest rank among all roles assigned to the caller."""
    grantor_roles = perm.system_roles + [
        r for roles in perm.scoped_roles.values() for r in roles
    ]
    grantor_max_rank = 0
    for gr in grantor_roles:
        gr_obj = await role_repo.get_role(gr)
        if gr_obj and gr_obj.rank > grantor_max_rank:
            grantor_max_rank = gr_obj.rank
    return grantor_max_rank


async def _check_org_scope(db: AsyncSession, perm, eenheid_id: UUID) -> None:
    """Raise 403 if the caller cannot access the given eenheid."""
    from bouwmeester.core.org_context import build_org_context

    if perm.person_id is None:
        raise HTTPException(403, "Cannot manage roles without an identified user")
    person_obj = await db.get(Person, perm.person_id)
    if person_obj is None:
        raise HTTPException(403, "Cannot manage roles without an identified user")
    org_ctx = await build_org_context(db, person_obj)
    if not org_ctx.is_admin and eenheid_id not in org_ctx.visible_eenheid_ids:
        raise HTTPException(
            403,
            "Cannot manage roles outside your org scope",
        )


@router.get("", response_model=list[RoleWithPermissionsResponse])
async def list_roles(
    _user: OptionalUser,
    db: AsyncSession = Depends(get_db),
):
    """List all defined roles with their permissions."""
    repo = RoleRepository(db)
    roles = await repo.list_roles()
    result = []
    for role in roles:
        perm_ids = await repo.get_role_permission_ids(role.id)
        result.append(
            RoleWithPermissionsResponse(
                id=role.id,
                naam=role.naam,
                description=role.description,
                level=role.level,
                rank=role.rank,
                permissions=sorted(perm_ids),
            )
        )
    return result


@router.get(
    "/my-permissions",
    response_model=MyPermissionsResponse,
)
async def my_permissions(
    user: OptionalUser,
    person_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Return the current user's roles and resolved permissions.

    In dev mode (no OIDC), accepts an optional person_id query param
    to resolve permissions for a specific person.
    """
    effective_user = user
    if effective_user is None and person_id is not None:
        effective_user = await db.get(Person, person_id)
    if effective_user is None:
        return MyPermissionsResponse(roles=[], permissions=[])
    perm_ctx = await build_permission_context(db, effective_user)
    pr_repo = PersonRoleRepository(db)
    assignments = await pr_repo.list_for_person(effective_user.id)
    roles = [_assignment_to_response(a) for a in assignments]
    scoped: dict[str, list[str]] = {}
    if not perm_ctx.is_super_admin:
        scoped = {
            str(eid): sorted(perms)
            for eid, perms in perm_ctx.scoped_permissions.items()
        }
    return MyPermissionsResponse(
        roles=roles,
        permissions=sorted(perm_ctx.effective_permissions),
        scoped_permissions=scoped,
    )


@router.get(
    "/persons/{person_id}/assignments",
    response_model=list[PersonRoleResponse],
)
async def list_person_roles(
    person_id: UUID,
    _perm=Depends(require_permission("people:read")),
    db: AsyncSession = Depends(get_db),
):
    """List role assignments for a person."""
    repo = PersonRoleRepository(db)
    assignments = await repo.list_for_person(person_id)
    return [_assignment_to_response(a) for a in assignments]


@router.post("/assign", response_model=PersonRoleResponse)
async def assign_role(
    data: PersonRoleCreate,
    perm=Depends(require_permission("people:assign_role")),
    db: AsyncSession = Depends(get_db),
):
    """Assign a role to a person."""
    # Validate role exists
    role_repo = RoleRepository(db)
    role = await role_repo.get_role(data.role_id)
    if role is None:
        raise HTTPException(404, f"Role '{data.role_id}' not found")

    # System-level roles require no eenheid
    if role.level == "system" and data.organisatie_eenheid_id:
        raise HTTPException(
            400,
            "System-level roles cannot be scoped to an eenheid",
        )
    if role.level != "system" and not data.organisatie_eenheid_id:
        raise HTTPException(
            400,
            f"Role '{data.role_id}' requires an organisatie_eenheid_id",
        )

    # Scope enforcement: can only assign roles you outrank,
    # and only within eenheden you have access to
    if not perm.is_super_admin:
        grantor_max_rank = await _get_max_rank(perm, role_repo)
        if role.rank >= grantor_max_rank:
            raise HTTPException(
                403,
                "Cannot assign a role at or above your own level",
            )
        if data.organisatie_eenheid_id:
            await _check_org_scope(db, perm, data.organisatie_eenheid_id)

    repo = PersonRoleRepository(db)
    grantor_id = perm.person_id if perm.person_id else None
    try:
        assignment = await repo.assign(
            person_id=data.person_id,
            role_id=data.role_id,
            organisatie_eenheid_id=data.organisatie_eenheid_id,
            granted_by_id=grantor_id,
            start_datum=data.start_datum or date.today(),
            eind_datum=data.eind_datum,
        )
    except IntegrityError:
        raise HTTPException(409, "Role assignment already exists")

    await log_activity(
        db,
        None,
        grantor_id,
        "role.assigned",
        details={
            "person_id": str(data.person_id),
            "role_id": data.role_id,
            "eenheid_id": (
                str(data.organisatie_eenheid_id)
                if data.organisatie_eenheid_id
                else None
            ),
        },
    )

    return _assignment_to_response(assignment)


@router.delete("/assignments/{assignment_id}")
async def revoke_role(
    assignment_id: UUID,
    _perm=Depends(require_permission("people:assign_role")),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a role assignment."""
    repo = PersonRoleRepository(db)
    # Read before delete for logging
    assignment = await repo.get_by_id(assignment_id)
    if assignment is None:
        raise HTTPException(404, "Assignment not found")

    # Guard: cannot revoke your own super_admin role
    if assignment.role_id == "super_admin" and assignment.person_id == _perm.person_id:
        raise HTTPException(
            400,
            "Je kunt je eigen systeembeheerder-rol niet intrekken",
        )

    # Scope enforcement: same rules as assign_role
    if not _perm.is_super_admin:
        role_repo = RoleRepository(db)
        target_role = await role_repo.get_role(assignment.role_id)

        grantor_max_rank = await _get_max_rank(_perm, role_repo)
        if target_role and target_role.rank >= grantor_max_rank:
            raise HTTPException(
                403,
                "Cannot revoke a role at or above your own level",
            )
        if assignment.organisatie_eenheid_id:
            await _check_org_scope(db, _perm, assignment.organisatie_eenheid_id)

    await repo.revoke(assignment_id)

    await log_activity(
        db,
        None,
        _perm.person_id,
        "role.revoked",
        details={
            "person_id": str(assignment.person_id),
            "role_id": assignment.role_id,
            "eenheid_id": (
                str(assignment.organisatie_eenheid_id)
                if assignment.organisatie_eenheid_id
                else None
            ),
        },
    )

    return {"ok": True}
