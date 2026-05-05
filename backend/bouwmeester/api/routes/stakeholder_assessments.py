"""API routes for StakeholderAssessment."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_found
from bouwmeester.api.routes.initiatief import _require_access
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import (
    PermissionContext,
    get_permission_context,
)
from bouwmeester.repositories.initiatief import InitiatiefRepository
from bouwmeester.repositories.stakeholder_assessment import (
    StakeholderAssessmentRepository,
)
from bouwmeester.schema.stakeholder_assessment import (
    StakeholderAssessmentCreate,
    StakeholderAssessmentResponse,
    StakeholderAssessmentUpdate,
    StakeholderScopeType,
)

router = APIRouter(prefix="/stakeholder-assessments", tags=["stakeholder-assessments"])


def _to_response(obj) -> StakeholderAssessmentResponse:
    return StakeholderAssessmentResponse(
        id=obj.id,
        person_id=obj.person_id,
        person_naam=obj.person.naam if obj.person else "",
        scope_type=obj.scope_type,
        scope_id=obj.scope_id,
        belang=obj.belang,
        houding=obj.houding,
        invloed=obj.invloed,
        notitie=obj.notitie,
        assessed_by_id=obj.assessed_by_id,
        assessed_by_naam=obj.assessed_by.naam if obj.assessed_by else None,
        assessed_at=obj.assessed_at,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    )


async def _check_scope_access(
    db: AsyncSession,
    scope_type: str,
    scope_id: UUID,
    current_user: OptionalUser,
    perm_ctx: PermissionContext,
    *,
    write: bool,
) -> None:
    """Verify the caller may read (or write) assessments on the given scope.

    Raises 403/404 on denial. ``write=True`` requires contributor-level on
    initiatief or `node:update` on corpus_node; ``write=False`` requires
    viewer-level / `node:read`.
    """
    if scope_type == "initiatief":
        repo = InitiatiefRepository(db)
        require_found(await repo.get_by_id(scope_id), "Initiatief")
        await _require_access(
            repo,
            scope_id,
            current_user,
            perm_ctx,
            "contributor" if write else "viewer",
        )
        return
    if scope_type == "corpus_node":
        # Nodes have no per-record ACL today: tenant-wide reads gated by the
        # authn-middleware, mutations gated by node:update.
        if write and not perm_ctx.has_permission("node:update"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Geen rechten om stakeholder-assessment te wijzigen",
            )
        if not write and not perm_ctx.has_permission("node:read"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Geen rechten om stakeholder-assessments te lezen",
            )
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Onbekend scope_type: {scope_type}",
    )


@router.get("", response_model=list[StakeholderAssessmentResponse])
async def list_assessments(
    scope_type: StakeholderScopeType,
    scope_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> list[StakeholderAssessmentResponse]:
    await _check_scope_access(
        db, scope_type.value, scope_id, current_user, perm_ctx, write=False
    )
    repo = StakeholderAssessmentRepository(db)
    items = await repo.list_for_scope(scope_type.value, scope_id)
    return [_to_response(item) for item in items]


@router.post(
    "",
    response_model=StakeholderAssessmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_assessment(
    data: StakeholderAssessmentCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> StakeholderAssessmentResponse:
    await _check_scope_access(
        db,
        data.scope_type.value,
        data.scope_id,
        current_user,
        perm_ctx,
        write=True,
    )
    repo = StakeholderAssessmentRepository(db)
    assessed_by_id = current_user.id if current_user else None
    try:
        assessment = await repo.create(data, assessed_by_id=assessed_by_id)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assessment voor deze persoon en scope bestaat al",
        )
    return _to_response(assessment)


@router.put("/{id}", response_model=StakeholderAssessmentResponse)
async def update_assessment(
    id: UUID,
    data: StakeholderAssessmentUpdate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> StakeholderAssessmentResponse:
    repo = StakeholderAssessmentRepository(db)
    existing = require_found(await repo.get_by_id(id), "Assessment")
    await _check_scope_access(
        db,
        existing.scope_type,
        existing.scope_id,
        current_user,
        perm_ctx,
        write=True,
    )
    assessed_by_id = current_user.id if current_user else None
    assessment = require_found(
        await repo.update(id, data, assessed_by_id=assessed_by_id),
        "Assessment",
    )
    return _to_response(assessment)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assessment(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> None:
    repo = StakeholderAssessmentRepository(db)
    existing = require_found(await repo.get_by_id(id), "Assessment")
    await _check_scope_access(
        db,
        existing.scope_type,
        existing.scope_id,
        current_user,
        perm_ctx,
        write=True,
    )
    if not await repo.delete(id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assessment niet gevonden"
        )
