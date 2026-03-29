"""Unified resource permission management routes.

Provides generic CRUD for the resource_permission table, used
by frontend components that manage stakeholders, members, and
contacts across all resource types.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import get_db
from bouwmeester.core.org_context import OrgContext, get_org_context
from bouwmeester.core.permissions import (
    PermissionContext,
    check_resource_permission,
    get_permission_context,
    require_permission,
)
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.repositories.resource_permission import (
    ResourcePermissionRepository,
)
from bouwmeester.schema.resource_permission import (
    PersonResourcePermissionResponse,
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


async def _get_resource_eenheid_id(
    db: AsyncSession,
    resource_type: str,
    resource_id: UUID,
) -> UUID | None:
    """Resolve the organisatie_eenheid_id for a polymorphic resource."""
    if resource_type == "corpus_node":
        from bouwmeester.models.corpus_node import CorpusNode

        stmt = select(CorpusNode.organisatie_eenheid_id).where(
            CorpusNode.id == resource_id
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    if resource_type == "opdracht":
        from bouwmeester.models.opdracht import Opdracht

        stmt = select(Opdracht.opdrachtgever_id).where(Opdracht.id == resource_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    if resource_type == "initiatief":
        from bouwmeester.models.initiatief import InitiatiefEenheid

        stmt = select(InitiatiefEenheid.eenheid_id).where(
            InitiatiefEenheid.initiatief_id == resource_id
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    if resource_type == "lead":
        from bouwmeester.models.initiatief import InitiatiefEenheid
        from bouwmeester.models.lead import Lead

        stmt = (
            select(InitiatiefEenheid.eenheid_id)
            .join(Lead, Lead.initiatief_id == InitiatiefEenheid.initiatief_id)
            .where(Lead.id == resource_id)
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    return None


async def _require_manage_permission(
    perm: PermissionContext,
    db: AsyncSession,
    resource_type: str,
    resource_id: UUID,
    org_ctx: OrgContext | None = None,
) -> None:
    """Check that the caller can manage permissions on the given resource.

    Checks both RBAC permissions and org scope: the resource must belong
    to an eenheid within the caller's visible scope.
    """
    if perm.is_super_admin:
        return
    has_resource = await check_resource_permission(
        db,
        perm.person_id,  # type: ignore[arg-type]
        resource_type,
        resource_id,
        "resource_permission:manage",
    )
    if has_resource:
        return

    has_rbac = perm.has_permission("resource_permission:manage")
    if not has_rbac:
        raise HTTPException(403, "Insufficient permissions")

    # RBAC grants the permission, but check org scope: the resource
    # must belong to an eenheid the caller can see.
    eenheid_id = await _get_resource_eenheid_id(db, resource_type, resource_id)
    if eenheid_id is not None and org_ctx is not None:
        if (
            not org_ctx.is_admin
            and eenheid_id not in org_ctx.visible_eenheid_ids
            and eenheid_id not in org_ctx.shared_eenheid_ids
        ):
            raise HTTPException(403, "Resource valt buiten je organisatiescope")


def _to_response(rp: ResourcePermission) -> ResourcePermissionResponse:
    return ResourcePermissionResponse(
        id=rp.id,
        person_id=rp.person_id,
        person=rp.person,
        resource_type=rp.resource_type,
        resource_id=rp.resource_id,
        rol=rp.rol,
        created_at=rp.created_at,
    )


async def _resolve_resource_names(
    db: AsyncSession,
    permissions: list[ResourcePermission],
) -> dict[UUID, str]:
    """Batch-resolve display names for polymorphic resource_ids."""
    from bouwmeester.models.corpus_node import CorpusNode
    from bouwmeester.models.initiatief import Initiatief
    from bouwmeester.models.lead import Lead
    from bouwmeester.models.opdracht import Opdracht
    from bouwmeester.models.team import Team

    table_map: dict[str, tuple] = {
        "corpus_node": (CorpusNode, CorpusNode.title),
        "initiatief": (Initiatief, Initiatief.naam),
        "lead": (Lead, Lead.title),
        "team": (Team, Team.naam),
        "opdracht": (Opdracht, Opdracht.titel),
    }

    ids_by_type: dict[str, set[UUID]] = {}
    for rp in permissions:
        ids_by_type.setdefault(rp.resource_type, set()).add(rp.resource_id)

    names: dict[UUID, str] = {}
    for rtype, ids in ids_by_type.items():
        if rtype not in table_map:
            continue
        model, name_col = table_map[rtype]
        stmt = select(model.id, name_col).where(model.id.in_(ids))
        result = await db.execute(stmt)
        for rid, rname in result.all():
            names[rid] = rname or str(rid)

    return names


@router.get(
    "/by-person/{person_id}",
    response_model=list[PersonResourcePermissionResponse],
)
async def list_person_resource_permissions(
    person_id: UUID,
    _perm=Depends(require_permission("people:read")),
    db: AsyncSession = Depends(get_db),
):
    """List all resource permissions for a person, with resolved names."""
    repo = ResourcePermissionRepository(db)
    perms = await repo.list_for_person(person_id)
    names = await _resolve_resource_names(db, perms)
    return [
        PersonResourcePermissionResponse(
            id=rp.id,
            person_id=rp.person_id,
            person=rp.person,
            resource_type=rp.resource_type,
            resource_id=rp.resource_id,
            rol=rp.rol,
            created_at=rp.created_at,
            resource_name=names.get(rp.resource_id, str(rp.resource_id)),
        )
        for rp in perms
    ]


@router.get(
    "/{resource_type}/{resource_id}",
    response_model=list[ResourcePermissionResponse],
)
async def list_resource_permissions(
    resource_type: str,
    resource_id: UUID,
    perm: PermissionContext = Depends(get_permission_context),
    org_ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """List people and roles on a resource."""
    _validate_resource_type(resource_type)
    if not perm.is_authenticated:
        raise HTTPException(401, "Not authenticated")
    await _require_manage_permission(perm, db, resource_type, resource_id, org_ctx)

    repo = ResourcePermissionRepository(db)
    perms = await repo.list_for_resource(resource_type, resource_id)
    return [_to_response(rp) for rp in perms]


@router.post(
    "/{resource_type}/{resource_id}",
    response_model=ResourcePermissionResponse,
)
async def add_resource_permission(
    resource_type: str,
    resource_id: UUID,
    data: ResourcePermissionCreate,
    perm: PermissionContext = Depends(get_permission_context),
    org_ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """Add a person to a resource with a role."""
    _validate_resource_type(resource_type)
    if not perm.is_authenticated:
        raise HTTPException(401, "Not authenticated")
    await _require_manage_permission(perm, db, resource_type, resource_id, org_ctx)

    repo = ResourcePermissionRepository(db)
    try:
        rp = await repo.create_permission(
            person_id=data.person_id,
            resource_type=resource_type,
            resource_id=resource_id,
            rol=data.rol,
        )
    except IntegrityError:
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

    return _to_response(rp)


@router.put(
    "/{rp_id}",
    response_model=ResourcePermissionResponse,
)
async def update_resource_permission(
    rp_id: UUID,
    data: ResourcePermissionUpdate,
    perm: PermissionContext = Depends(get_permission_context),
    org_ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """Change a resource permission's role."""
    if not perm.is_authenticated:
        raise HTTPException(401, "Not authenticated")

    repo = ResourcePermissionRepository(db)
    rp = await repo.get_with_person(rp_id)
    if rp is None:
        raise HTTPException(404, "Permission not found")
    await _require_manage_permission(
        perm, db, rp.resource_type, rp.resource_id, org_ctx
    )

    rp.rol = data.rol
    await db.flush()
    await db.refresh(rp)
    return _to_response(rp)


@router.delete("/{rp_id}")
async def delete_resource_permission(
    rp_id: UUID,
    perm: PermissionContext = Depends(get_permission_context),
    org_ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """Remove a resource permission."""
    if not perm.is_authenticated:
        raise HTTPException(401, "Not authenticated")

    repo = ResourcePermissionRepository(db)
    rp = await repo.get_with_person(rp_id)
    if rp is None:
        raise HTTPException(404, "Permission not found")
    await _require_manage_permission(
        perm, db, rp.resource_type, rp.resource_id, org_ctx
    )

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
