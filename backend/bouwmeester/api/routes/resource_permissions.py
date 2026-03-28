"""Unified resource permission management routes.

Provides generic CRUD for the resource_permission table, used
by frontend components that manage stakeholders, members, and
contacts across all resource types.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import (
    PermissionContext,
    check_resource_permission,
    get_permission_context,
)
from bouwmeester.repositories.resource_permission import (
    ResourcePermissionRepository,
)
from bouwmeester.schema.resource_permission import (
    ResourcePermissionCreate,
    ResourcePermissionResponse,
    ResourcePermissionUpdate,
)
from bouwmeester.services.activity_service import log_activity

router = APIRouter(
    prefix="/resource-permissions",
    tags=["resource-permissions"],
)

VALID_RESOURCE_TYPES = {
    "corpus_node",
    "initiatief",
    "lead",
    "team",
    "opdracht",
}


def _validate_resource_type(resource_type: str) -> None:
    if resource_type not in VALID_RESOURCE_TYPES:
        raise HTTPException(
            400,
            f"Invalid resource_type: {resource_type}",
        )


@router.get(
    "/{resource_type}/{resource_id}",
    response_model=list[ResourcePermissionResponse],
)
async def list_resource_permissions(
    resource_type: str,
    resource_id: UUID,
    perm: PermissionContext = Depends(get_permission_context),
    db: AsyncSession = Depends(get_db),
):
    """List people and roles on a resource."""
    _validate_resource_type(resource_type)
    if not perm.is_authenticated:
        raise HTTPException(401, "Not authenticated")

    # Require RBAC permission or resource-level access
    if not perm.is_super_admin:
        has_rbac = perm.has_permission("resource_permission:manage")
        has_resource = await check_resource_permission(
            db,
            perm.person_id,  # type: ignore[arg-type]
            resource_type,
            resource_id,
            "resource_permission:manage",
        )
        if not has_rbac and not has_resource:
            raise HTTPException(403, "Insufficient permissions")

    repo = ResourcePermissionRepository(db)
    perms = await repo.list_for_resource(resource_type, resource_id)
    return [
        ResourcePermissionResponse(
            id=rp.id,
            person_id=rp.person_id,
            person=rp.person,
            resource_type=rp.resource_type,
            resource_id=rp.resource_id,
            rol=rp.rol,
            created_at=rp.created_at,
        )
        for rp in perms
    ]


@router.post(
    "/{resource_type}/{resource_id}",
    response_model=ResourcePermissionResponse,
)
async def add_resource_permission(
    resource_type: str,
    resource_id: UUID,
    data: ResourcePermissionCreate,
    perm: PermissionContext = Depends(get_permission_context),
    db: AsyncSession = Depends(get_db),
):
    """Add a person to a resource with a role."""
    _validate_resource_type(resource_type)
    if not perm.is_authenticated:
        raise HTTPException(401, "Not authenticated")

    # Check: user needs resource_permission:manage via RBAC
    # or eigenaar role on this resource
    if not perm.is_super_admin:
        has_rbac = perm.has_permission("resource_permission:manage")
        has_resource = await check_resource_permission(
            db,
            perm.person_id,  # type: ignore[arg-type]
            resource_type,
            resource_id,
            "resource_permission:manage",
        )
        if not has_rbac and not has_resource:
            raise HTTPException(403, "Insufficient permissions")

    repo = ResourcePermissionRepository(db)
    try:
        rp = await repo.create_permission(
            person_id=data.person_id,
            resource_type=resource_type,
            resource_id=resource_id,
            rol=data.rol,
        )
    except Exception:
        raise HTTPException(
            409,
            "Permission already exists",
        )

    await log_activity(
        db,
        None,
        perm.person_id,
        "resource_permission.added",
        details={
            "resource_type": resource_type,
            "resource_id": str(resource_id),
            "person_id": str(data.person_id),
            "rol": data.rol,
        },
    )

    return ResourcePermissionResponse(
        id=rp.id,
        person_id=rp.person_id,
        person=rp.person,
        resource_type=rp.resource_type,
        resource_id=rp.resource_id,
        rol=rp.rol,
        created_at=rp.created_at,
    )


@router.put(
    "/{rp_id}",
    response_model=ResourcePermissionResponse,
)
async def update_resource_permission(
    rp_id: UUID,
    data: ResourcePermissionUpdate,
    perm: PermissionContext = Depends(get_permission_context),
    db: AsyncSession = Depends(get_db),
):
    """Change a resource permission's role."""
    if not perm.is_authenticated:
        raise HTTPException(401, "Not authenticated")

    repo = ResourcePermissionRepository(db)
    rp = await repo.get_with_person(rp_id)
    if rp is None:
        raise HTTPException(404, "Permission not found")

    if not perm.is_super_admin:
        has_rbac = perm.has_permission("resource_permission:manage")
        has_resource = await check_resource_permission(
            db,
            perm.person_id,  # type: ignore[arg-type]
            rp.resource_type,
            rp.resource_id,
            "resource_permission:manage",
        )
        if not has_rbac and not has_resource:
            raise HTTPException(403, "Insufficient permissions")

    rp.rol = data.rol
    await db.flush()
    await db.refresh(rp)
    return ResourcePermissionResponse(
        id=rp.id,
        person_id=rp.person_id,
        person=rp.person,
        resource_type=rp.resource_type,
        resource_id=rp.resource_id,
        rol=rp.rol,
        created_at=rp.created_at,
    )


@router.delete("/{rp_id}")
async def delete_resource_permission(
    rp_id: UUID,
    perm: PermissionContext = Depends(get_permission_context),
    db: AsyncSession = Depends(get_db),
):
    """Remove a resource permission."""
    if not perm.is_authenticated:
        raise HTTPException(401, "Not authenticated")

    repo = ResourcePermissionRepository(db)
    rp = await repo.get_with_person(rp_id)
    if rp is None:
        raise HTTPException(404, "Permission not found")

    if not perm.is_super_admin:
        has_rbac = perm.has_permission("resource_permission:manage")
        has_resource = await check_resource_permission(
            db,
            perm.person_id,  # type: ignore[arg-type]
            rp.resource_type,
            rp.resource_id,
            "resource_permission:manage",
        )
        if not has_rbac and not has_resource:
            raise HTTPException(403, "Insufficient permissions")

    await log_activity(
        db,
        None,
        perm.person_id,
        "resource_permission.removed",
        details={
            "resource_type": rp.resource_type,
            "resource_id": str(rp.resource_id),
            "person_id": str(rp.person_id),
            "rol": rp.rol,
        },
    )

    await repo.delete(rp_id)
    return {"ok": True}
