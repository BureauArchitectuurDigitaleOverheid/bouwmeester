"""API routes for initiatieven."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_deleted, require_found, validate_list
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.initiatief_context import (
    InitiatiefContext,
    get_initiatief_context,
)
from bouwmeester.repositories.initiatief import InitiatiefRepository
from bouwmeester.schema.initiatief import (
    InitiatiefCreate,
    InitiatiefDetailResponse,
    InitiatiefEenheidCreate,
    InitiatiefEenheidResponse,
    InitiatiefMemberCreate,
    InitiatiefMemberResponse,
    InitiatiefResponse,
    InitiatiefUpdate,
)
from bouwmeester.services.activity_service import log_activity

router = APIRouter(prefix="/initiatieven", tags=["initiatieven"])


async def _require_eigenaar(
    repo: InitiatiefRepository,
    initiatief_id: UUID,
    user: OptionalUser,
) -> None:
    """Raise 403 unless user is eigenaar or admin."""
    if not user:
        return  # dev mode, no OIDC
    if user.is_admin:
        return
    role = await repo.get_member_role(initiatief_id, user.id)
    if role != "eigenaar":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Alleen de eigenaar mag dit doen",
        )


async def _require_member_or_admin(
    repo: InitiatiefRepository,
    initiatief_id: UUID,
    user: OptionalUser,
) -> None:
    """Raise 404 unless user is a member (direct or via eenheid) or admin."""
    if not user:
        return  # dev mode
    if user.is_admin:
        return
    if not await repo.is_member(initiatief_id, user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Initiatief niet gevonden",
        )


@router.get("", response_model=list[InitiatiefResponse])
async def list_initiatieven(
    current_user: OptionalUser,
    search: str | None = Query(None, max_length=200),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> list[InitiatiefResponse]:
    repo = InitiatiefRepository(db)
    items = await repo.get_all(skip=skip, limit=limit, search=search, init_ctx=init_ctx)
    return validate_list(InitiatiefResponse, items)


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
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> InitiatiefDetailResponse:
    repo = InitiatiefRepository(db)
    initiatief = require_found(await repo.get_detail(id), "Initiatief")
    await _require_member_or_admin(repo, id, current_user)
    # Build response with member/eenheid names
    from bouwmeester.repositories.resource_permission import (
        ResourcePermissionRepository,
    )

    rp_repo = ResourcePermissionRepository(db)
    rp_members = await rp_repo.list_for_resource("initiatief", id)
    members = [
        InitiatiefMemberResponse(
            initiatief_id=rp.resource_id,
            person_id=rp.person_id,
            person_naam=rp.person.naam if rp.person else "",
            rol=rp.rol,
            created_at=rp.created_at,
        )
        for rp in rp_members
    ]
    eenheden = []
    for e in initiatief.eenheden:
        eenheden.append(
            InitiatiefEenheidResponse(
                initiatief_id=e.initiatief_id,
                eenheid_id=e.eenheid_id,
                eenheid_naam=e.eenheid.naam if e.eenheid else "",
                created_at=e.created_at,
            )
        )
    resp = InitiatiefDetailResponse.model_validate(initiatief)
    resp.members = members
    resp.eenheden = eenheden
    return resp


@router.put("/{id}", response_model=InitiatiefResponse)
async def update_initiatief(
    id: UUID,
    data: InitiatiefUpdate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> InitiatiefResponse:
    repo = InitiatiefRepository(db)
    await _require_eigenaar(repo, id, current_user)
    initiatief = require_found(await repo.update(id, data), "Initiatief")

    await log_activity(
        db,
        current_user,
        None,
        "initiatief.updated",
        details={"initiatief_id": str(initiatief.id), "naam": initiatief.naam},
    )

    return InitiatiefResponse.model_validate(initiatief)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_initiatief(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = InitiatiefRepository(db)
    await _require_eigenaar(repo, id, current_user)
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
) -> InitiatiefMemberResponse:
    repo = InitiatiefRepository(db)
    require_found(await repo.get_by_id(id), "Initiatief")
    await _require_eigenaar(repo, id, current_user)
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
) -> None:
    repo = InitiatiefRepository(db)
    await _require_eigenaar(repo, id, current_user)
    # Prevent removing the last eigenaar
    current_role = await repo.get_member_role(id, person_id)
    if current_role == "eigenaar":
        eigenaar_count = await repo.count_eigenaren(id)
        if eigenaar_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Er moet tenminste 1 eigenaar zijn",
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
) -> InitiatiefMemberResponse:
    """Update a member's role (e.g. promote to eigenaar)."""
    repo = InitiatiefRepository(db)
    await _require_eigenaar(repo, id, current_user)
    # Prevent demoting the last eigenaar
    if data.rol != "eigenaar":
        eigenaar_count = await repo.count_eigenaren(id)
        current_role = await repo.get_member_role(id, person_id)
        if current_role == "eigenaar" and eigenaar_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Er moet tenminste 1 eigenaar zijn",
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
) -> InitiatiefEenheidResponse:
    repo = InitiatiefRepository(db)
    require_found(await repo.get_by_id(id), "Initiatief")
    await _require_eigenaar(repo, id, current_user)
    link = await repo.add_eenheid(id, data.eenheid_id)

    await log_activity(
        db,
        current_user,
        None,
        "initiatief_eenheid.added",
        details={"initiatief_id": str(id), "eenheid_id": str(data.eenheid_id)},
    )

    return InitiatiefEenheidResponse(
        initiatief_id=link.initiatief_id,
        eenheid_id=link.eenheid_id,
        eenheid_naam=link.eenheid.naam if link.eenheid else "",
        created_at=link.created_at,
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
) -> None:
    repo = InitiatiefRepository(db)
    await _require_eigenaar(repo, id, current_user)
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
