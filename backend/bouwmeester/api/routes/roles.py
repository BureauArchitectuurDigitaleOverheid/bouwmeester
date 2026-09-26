"""Role management API routes."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.authz import require_can_assign_role, require_can_revoke_role
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
    system: list[str] = []
    if not perm_ctx.is_super_admin:
        scoped = {
            str(eid): sorted(perms)
            for eid, perms in perm_ctx.scoped_permissions.items()
        }
        system = sorted(perm_ctx.system_permissions)
    return MyPermissionsResponse(
        roles=roles,
        permissions=sorted(perm_ctx.effective_permissions),
        scoped_permissions=scoped,
        system_permissions=system,
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


@router.get(
    "/eenheid/{eenheid_id}/assignments",
    response_model=list[PersonRoleResponse],
)
async def list_eenheid_roles(
    eenheid_id: UUID,
    _perm=Depends(require_permission("people:assign_role")),
    db: AsyncSession = Depends(get_db),
):
    """List role assignments scoped to an eenheid."""
    repo = PersonRoleRepository(db)
    assignments = await repo.list_for_eenheid(eenheid_id)
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

    await require_can_assign_role(
        db,
        perm,
        role=role,
        eenheid_id=data.organisatie_eenheid_id,
        target_person_id=data.person_id,
    )

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

    await require_can_revoke_role(db, _perm, assignment)

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
