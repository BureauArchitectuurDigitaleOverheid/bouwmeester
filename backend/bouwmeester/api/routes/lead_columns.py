"""API routes for per-initiatief funnel-kolommen."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_found
from bouwmeester.api.routes.initiatief import (
    _require_access,
    _resolve_access_level,
)
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import (
    PermissionContext,
    get_permission_context,
)
from bouwmeester.repositories.initiatief import InitiatiefRepository
from bouwmeester.repositories.lead_column import LeadColumnRepository
from bouwmeester.schema.lead_column import (
    LeadColumnCreate,
    LeadColumnReorder,
    LeadColumnResponse,
    LeadColumnUpdate,
)
from bouwmeester.services.activity_service import log_activity

router = APIRouter(prefix="/initiatieven", tags=["lead-columns"])


def _to_response(column, lead_count: int = 0) -> LeadColumnResponse:
    return LeadColumnResponse(
        id=column.id,
        initiatief_id=column.initiatief_id,
        name=column.name,
        slug=column.slug,
        sort_order=column.sort_order,
        color=column.color,
        is_active_stage=column.is_active_stage,
        is_public_visible=column.is_public_visible,
        lead_count=lead_count,
        created_at=column.created_at,
        updated_at=column.updated_at,
    )


@router.get(
    "/{initiatief_id}/columns",
    response_model=list[LeadColumnResponse],
)
async def list_columns(
    initiatief_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> list[LeadColumnResponse]:
    """List funnel-kolommen for an initiatief. Any member with access."""
    init_repo = InitiatiefRepository(db)
    require_found(await init_repo.get_by_id(initiatief_id), "Initiatief")
    access_level = await _resolve_access_level(
        init_repo, initiatief_id, current_user, perm_ctx
    )
    if access_level is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Geen toegang tot dit initiatief",
        )

    repo = LeadColumnRepository(db)
    columns = await repo.list_for_initiatief(initiatief_id)
    counts = await repo.lead_counts_for_initiatief(initiatief_id)
    return [_to_response(c, counts.get(c.slug, 0)) for c in columns]


@router.post(
    "/{initiatief_id}/columns",
    response_model=LeadColumnResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_column(
    initiatief_id: UUID,
    data: LeadColumnCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> LeadColumnResponse:
    """Create a new funnel-kolom. Eigenaar only."""
    init_repo = InitiatiefRepository(db)
    require_found(await init_repo.get_by_id(initiatief_id), "Initiatief")
    await _require_access(init_repo, initiatief_id, current_user, perm_ctx, "eigenaar")

    repo = LeadColumnRepository(db)
    if await repo.slug_or_name_exists(initiatief_id, name=data.name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Een kolom met deze naam bestaat al",
        )
    column = await repo.create(initiatief_id, data)

    await log_activity(
        db,
        current_user,
        None,
        "lead_column.created",
        details={
            "initiatief_id": str(initiatief_id),
            "column_id": str(column.id),
            "name": column.name,
            "slug": column.slug,
        },
    )

    return _to_response(column, 0)


@router.put(
    "/{initiatief_id}/columns/{column_id}",
    response_model=LeadColumnResponse,
)
async def update_column(
    initiatief_id: UUID,
    column_id: UUID,
    data: LeadColumnUpdate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> LeadColumnResponse:
    """Update a funnel-kolom (name/color/flags). Slug is immutable. Eigenaar only."""
    init_repo = InitiatiefRepository(db)
    require_found(await init_repo.get_by_id(initiatief_id), "Initiatief")
    await _require_access(init_repo, initiatief_id, current_user, perm_ctx, "eigenaar")

    repo = LeadColumnRepository(db)
    existing = await repo.get(column_id)
    if existing is None or existing.initiatief_id != initiatief_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Kolom niet gevonden"
        )
    if data.name is not None and data.name != existing.name:
        if await repo.slug_or_name_exists(
            initiatief_id, name=data.name, exclude_id=column_id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Een kolom met deze naam bestaat al",
            )
    column = await repo.update(column_id, data)

    await log_activity(
        db,
        current_user,
        None,
        "lead_column.updated",
        details={
            "initiatief_id": str(initiatief_id),
            "column_id": str(column_id),
            "fields": list(data.model_dump(exclude_unset=True).keys()),
        },
    )

    counts = await repo.lead_counts_for_initiatief(initiatief_id)
    return _to_response(column, counts.get(column.slug, 0))


@router.delete(
    "/{initiatief_id}/columns/{column_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_column(
    initiatief_id: UUID,
    column_id: UUID,
    current_user: OptionalUser,
    move_to: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> None:
    """Delete a kolom. Migrates leads to ``move_to`` if non-empty (eigenaar)."""
    init_repo = InitiatiefRepository(db)
    require_found(await init_repo.get_by_id(initiatief_id), "Initiatief")
    await _require_access(init_repo, initiatief_id, current_user, perm_ctx, "eigenaar")

    repo = LeadColumnRepository(db)
    deleted, error = await repo.delete_with_move(initiatief_id, column_id, move_to)
    if not deleted:
        if error == "not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Kolom niet gevonden",
            )
        if error == "last_column":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Er moet tenminste 1 kolom zijn",
            )
        if error == "leads_present":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Kolom bevat leads; geef move_to mee om ze te verplaatsen",
            )
        if error == "invalid_target":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ongeldige doel-kolom voor move_to",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kon kolom niet verwijderen",
        )

    await log_activity(
        db,
        current_user,
        None,
        "lead_column.deleted",
        details={
            "initiatief_id": str(initiatief_id),
            "column_id": str(column_id),
            "move_to": str(move_to) if move_to else None,
        },
    )


@router.post(
    "/{initiatief_id}/columns/reorder",
    response_model=list[LeadColumnResponse],
)
async def reorder_columns(
    initiatief_id: UUID,
    data: LeadColumnReorder,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> list[LeadColumnResponse]:
    """Reorder kolommen. Body must list every column id (eigenaar)."""
    init_repo = InitiatiefRepository(db)
    require_found(await init_repo.get_by_id(initiatief_id), "Initiatief")
    await _require_access(init_repo, initiatief_id, current_user, perm_ctx, "eigenaar")

    repo = LeadColumnRepository(db)
    ok, error = await repo.reorder(initiatief_id, data.column_ids)
    if not ok:
        if error == "mismatch":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "column_ids moet exact alle kolommen van het initiatief bevatten"
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kon kolommen niet herordenen",
        )

    await log_activity(
        db,
        current_user,
        None,
        "lead_column.reordered",
        details={"initiatief_id": str(initiatief_id)},
    )

    columns = await repo.list_for_initiatief(initiatief_id)
    counts = await repo.lead_counts_for_initiatief(initiatief_id)
    return [_to_response(c, counts.get(c.slug, 0)) for c in columns]
