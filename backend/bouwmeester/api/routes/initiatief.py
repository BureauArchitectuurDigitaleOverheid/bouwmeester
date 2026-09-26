"""API routes for initiatieven."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_deleted, require_found
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.authority import (
    require_can_change_grants,
    require_can_grant_resource_role,
)
from bouwmeester.core.authz import requires
from bouwmeester.core.database import get_db
from bouwmeester.core.initiatief_context import (
    InitiatiefContext,
    get_initiatief_context,
    initiatief_access_level,
    require_initiatief_read,
)
from bouwmeester.core.permissions import (
    PermissionContext,
    get_permission_context,
)
from bouwmeester.repositories.initiatief import InitiatiefRepository
from bouwmeester.schema.initiatief import (
    InitiatiefCreate,
    InitiatiefDetailResponse,
    InitiatiefEenheidCreate,
    InitiatiefEenheidResponse,
    InitiatiefEenheidUpdate,
    InitiatiefEenheidWithNameResponse,
    InitiatiefListItemResponse,
    InitiatiefMemberCreate,
    InitiatiefMemberResponse,
    InitiatiefResponse,
    InitiatiefSettingsUpdate,
    InitiatiefUpdate,
)
from bouwmeester.services.activity_service import log_activity

router = APIRouter(prefix="/initiatieven", tags=["initiatieven"])


@router.get("", response_model=list[InitiatiefListItemResponse])
async def list_initiatieven(
    current_user: OptionalUser,
    search: str | None = Query(None, max_length=200),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> list[InitiatiefListItemResponse]:
    repo = InitiatiefRepository(db)
    items = await repo.get_all(skip=skip, limit=limit, search=search, init_ctx=init_ctx)
    stats = await repo.get_list_stats([i.id for i in items])
    return [
        InitiatiefListItemResponse.model_validate(i).model_copy(update=stats[i.id])
        for i in items
    ]


@router.post(
    "",
    response_model=InitiatiefResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_initiatief(
    data: InitiatiefCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> InitiatiefResponse:
    """Any logged-in user may start a personal initiatief.

    The creator becomes its eigenaar through a person-level resource role;
    the payload carries nothing else that grants access.  Linking an eenheid
    afterwards goes through the grant routes (``core.authority``).
    """
    repo = InitiatiefRepository(db)
    created_by_id = current_user.id if current_user else None
    initiatief = await repo.create(data, created_by_id=created_by_id)

    await log_activity(
        db,
        current_user,
        None,
        "initiatief.created",
        details={"initiatief_id": str(initiatief.id), "naam": initiatief.naam},
    )

    return InitiatiefResponse.model_validate(initiatief)


@router.get("/{id}", response_model=InitiatiefDetailResponse)
async def get_initiatief(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> InitiatiefDetailResponse:
    # The same visibility as the list; 404 hides existence.
    await require_initiatief_read(db, perm_ctx, id, init_ctx)
    repo = InitiatiefRepository(db)
    initiatief = require_found(await repo.get_detail(id), "Initiatief")
    access_level = await initiatief_access_level(db, perm_ctx, id, init_ctx)
    from bouwmeester.repositories.resource_permission import (
        ResourcePermissionRepository,
    )

    # Fetch all resource permissions for this initiatief

    rp_repo = ResourcePermissionRepository(db)
    all_perms = await rp_repo.list_for_resource("initiatief", id, include_eenheid=True)

    # Split into person-scoped (members) and eenheid-scoped
    members = [
        InitiatiefMemberResponse(
            initiatief_id=rp.resource_id,
            person_id=rp.person_id,
            person_naam=rp.person.naam if rp.person else "",
            rol=rp.rol,
            created_at=rp.created_at,
        )
        for rp in all_perms
        if rp.person_id is not None
    ]
    eenheden = [
        InitiatiefEenheidResponse(
            initiatief_id=rp.resource_id,
            eenheid_id=rp.organisatie_eenheid_id,
            eenheid_naam=rp.eenheid.naam if rp.eenheid else "",
            rol=rp.rol,
            created_at=rp.created_at,
        )
        for rp in all_perms
        if rp.organisatie_eenheid_id is not None
    ]
    resp = InitiatiefDetailResponse.model_validate(initiatief)
    resp.members = members
    resp.eenheden = eenheden
    resp.access_level = access_level
    return resp


@router.put("/{id}", response_model=InitiatiefResponse)
async def update_initiatief(
    id: UUID,
    data: InitiatiefUpdate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _authz=Depends(requires("initiatief:update", "initiatief")),
) -> InitiatiefResponse:
    repo = InitiatiefRepository(db)
    initiatief = require_found(await repo.update(id, data), "Initiatief")

    await log_activity(
        db,
        current_user,
        None,
        "initiatief.updated",
        details={"initiatief_id": str(initiatief.id), "naam": initiatief.naam},
    )

    return InitiatiefResponse.model_validate(initiatief)


@router.put("/{id}/settings", response_model=InitiatiefResponse)
async def update_initiatief_settings(
    id: UUID,
    data: InitiatiefSettingsUpdate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    # Eigenaar only: initiatief:delete is what only an eigenaar-level role has.
    _authz=Depends(requires("initiatief:delete", "initiatief")),
) -> InitiatiefResponse:
    """Update settings (slug, toggles, score-labels). Eigenaar only."""
    repo = InitiatiefRepository(db)
    initiatief = require_found(await repo.update_settings(id, data), "Initiatief")

    await log_activity(
        db,
        current_user,
        None,
        "initiatief.settings_updated",
        details={
            "initiatief_id": str(initiatief.id),
            "fields": list(data.model_dump(exclude_unset=True).keys()),
        },
    )

    return InitiatiefResponse.model_validate(initiatief)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_initiatief(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _authz=Depends(requires("initiatief:delete", "initiatief")),
) -> None:
    repo = InitiatiefRepository(db)
    initiatief = require_found(await repo.get_by_id(id), "Initiatief")
    initiatief_naam = initiatief.naam

    # Clean up resource_permission rows
    from sqlalchemy import delete as sa_delete

    from bouwmeester.models.resource_permission import ResourcePermission

    await db.execute(
        sa_delete(ResourcePermission).where(
            ResourcePermission.resource_type == "initiatief",
            ResourcePermission.resource_id == id,
        )
    )

    require_deleted(await repo.delete(id), "Initiatief")

    await log_activity(
        db,
        current_user,
        None,
        "initiatief.deleted",
        details={"initiatief_id": str(id), "naam": initiatief_naam},
    )


# ---------------------------------------------------------------------------
# Member management
# ---------------------------------------------------------------------------


@router.post(
    "/{id}/members",
    response_model=InitiatiefMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    id: UUID,
    data: InitiatiefMemberCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> InitiatiefMemberResponse:
    repo = InitiatiefRepository(db)
    require_found(await repo.get_by_id(id), "Initiatief")
    await require_can_grant_resource_role(
        db,
        perm_ctx,
        resource_type="initiatief",
        resource_id=id,
        rol=data.rol,
        target_person_id=data.person_id,
    )
    member = await repo.add_member(id, data.person_id, data.rol)

    await log_activity(
        db,
        current_user,
        None,
        "initiatief_member.added",
        details={
            "initiatief_id": str(id),
            "person_id": str(data.person_id),
            "rol": data.rol,
        },
    )

    return InitiatiefMemberResponse(
        initiatief_id=member.resource_id,
        person_id=member.person_id,
        person_naam=member.person.naam if member.person else "",
        rol=member.rol,
        created_at=member.created_at,
    )


@router.delete(
    "/{id}/members/{person_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    id: UUID,
    person_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> None:
    repo = InitiatiefRepository(db)
    await require_can_change_grants(
        db,
        perm_ctx,
        resource_type="initiatief",
        resource_id=id,
        person_id=person_id,
        new_rol=None,
    )
    if not await repo.remove_member(id, person_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lid niet gevonden",
        )

    await log_activity(
        db,
        current_user,
        None,
        "initiatief_member.removed",
        details={"initiatief_id": str(id), "person_id": str(person_id)},
    )


@router.put(
    "/{id}/members/{person_id}",
    response_model=InitiatiefMemberResponse,
)
async def update_member_role(
    id: UUID,
    person_id: UUID,
    data: InitiatiefMemberCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> InitiatiefMemberResponse:
    """Update a member's role (e.g. promote to eigenaar)."""
    repo = InitiatiefRepository(db)
    await require_can_change_grants(
        db,
        perm_ctx,
        resource_type="initiatief",
        resource_id=id,
        person_id=person_id,
        new_rol=data.rol,
    )
    member = await repo.update_member_role(id, person_id, data.rol)
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lid niet gevonden",
        )

    await log_activity(
        db,
        current_user,
        None,
        "initiatief_member.updated",
        details={
            "initiatief_id": str(id),
            "person_id": str(person_id),
            "rol": data.rol,
        },
    )

    return InitiatiefMemberResponse(
        initiatief_id=member.resource_id,
        person_id=member.person_id,
        person_naam=member.person.naam if member.person else "",
        rol=member.rol,
        created_at=member.created_at,
    )


# ---------------------------------------------------------------------------
# Eenheid management
# ---------------------------------------------------------------------------


@router.post(
    "/{id}/eenheden",
    response_model=InitiatiefEenheidResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_eenheid(
    id: UUID,
    data: InitiatiefEenheidCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> InitiatiefEenheidResponse:
    from sqlalchemy.exc import IntegrityError

    repo = InitiatiefRepository(db)
    require_found(await repo.get_by_id(id), "Initiatief")
    await require_can_grant_resource_role(
        db,
        perm_ctx,
        resource_type="initiatief",
        resource_id=id,
        rol=data.rol,
        target_eenheid_id=data.eenheid_id,
    )
    try:
        rp = await repo.add_eenheid(id, data.eenheid_id, data.rol)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Eenheid is al gekoppeld aan dit initiatief",
        )

    await log_activity(
        db,
        current_user,
        None,
        "initiatief_eenheid.added",
        details={
            "initiatief_id": str(id),
            "eenheid_id": str(data.eenheid_id),
            "rol": data.rol,
        },
    )

    return InitiatiefEenheidResponse(
        initiatief_id=rp.resource_id,
        eenheid_id=rp.organisatie_eenheid_id,
        eenheid_naam=rp.eenheid.naam if rp.eenheid else "",
        rol=rp.rol,
        created_at=rp.created_at,
    )


@router.delete(
    "/{id}/eenheden/{eenheid_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_eenheid(
    id: UUID,
    eenheid_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> None:
    repo = InitiatiefRepository(db)
    await require_can_change_grants(
        db,
        perm_ctx,
        resource_type="initiatief",
        resource_id=id,
        eenheid_id=eenheid_id,
        new_rol=None,
    )
    if not await repo.remove_eenheid(id, eenheid_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Eenheid niet gevonden",
        )

    await log_activity(
        db,
        current_user,
        None,
        "initiatief_eenheid.removed",
        details={"initiatief_id": str(id), "eenheid_id": str(eenheid_id)},
    )


@router.put(
    "/{id}/eenheden/{eenheid_id}",
    response_model=InitiatiefEenheidResponse,
)
async def update_eenheid_rol(
    id: UUID,
    eenheid_id: UUID,
    data: InitiatiefEenheidUpdate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> InitiatiefEenheidResponse:
    """Update an eenheid's role on this initiatief."""
    repo = InitiatiefRepository(db)
    await require_can_change_grants(
        db,
        perm_ctx,
        resource_type="initiatief",
        resource_id=id,
        eenheid_id=eenheid_id,
        new_rol=data.rol,
    )
    rp = await repo.update_eenheid_rol(id, eenheid_id, data.rol)
    if rp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Eenheid niet gevonden",
        )

    await log_activity(
        db,
        current_user,
        None,
        "initiatief_eenheid.updated",
        details={
            "initiatief_id": str(id),
            "eenheid_id": str(eenheid_id),
            "rol": data.rol,
        },
    )

    return InitiatiefEenheidResponse(
        initiatief_id=rp.resource_id,
        eenheid_id=rp.organisatie_eenheid_id,
        eenheid_naam=rp.eenheid.naam if rp.eenheid else "",
        rol=rp.rol,
        created_at=rp.created_at,
    )


# ---------------------------------------------------------------------------
# Eenheid → initiatieven (reverse lookup)
# ---------------------------------------------------------------------------


@router.get(
    "/by-eenheid/{eenheid_id}",
    response_model=list[InitiatiefEenheidWithNameResponse],
)
async def list_initiatieven_for_eenheid(
    eenheid_id: UUID,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> list[InitiatiefEenheidWithNameResponse]:
    """The visible initiatieven linked to an eenheid via resource_permission."""
    from bouwmeester.models.initiatief import Initiatief

    repo = InitiatiefRepository(db)
    perms = await repo.list_for_eenheid(eenheid_id, init_ctx)

    if not perms:
        return []

    # Batch load initiatief names (avoid N+1)
    initiatief_ids = [rp.resource_id for rp in perms]
    name_stmt = select(Initiatief.id, Initiatief.naam).where(
        Initiatief.id.in_(initiatief_ids)
    )
    name_result = await db.execute(name_stmt)
    names = dict(name_result.all())

    return [
        InitiatiefEenheidWithNameResponse(
            initiatief_id=rp.resource_id,
            initiatief_naam=names.get(rp.resource_id, ""),
            eenheid_id=rp.organisatie_eenheid_id,
            rol=rp.rol,
            created_at=rp.created_at,
        )
        for rp in perms
    ]
