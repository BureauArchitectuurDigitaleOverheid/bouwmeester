"""API routes for StakeholderAssessment."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_deleted, require_found
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.authz import require, requires
from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import (
    PermissionContext,
    get_permission_context,
)
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


@router.get("", response_model=list[StakeholderAssessmentResponse])
async def list_assessments(
    scope_type: StakeholderScopeType,
    scope_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> list[StakeholderAssessmentResponse]:
    # Readable when the scope (a node or an initiatief) is (``core.authz``).
    await require(
        db, perm_ctx, "stakeholder_assessment:read", scope_type.value, scope_id
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
    # Asked on the scope itself: node:update or initiatief:update there.
    await require(
        db,
        perm_ctx,
        "stakeholder_assessment:create",
        data.scope_type.value,
        data.scope_id,
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
    _authz=Depends(requires("stakeholder_assessment:update", "stakeholder_assessment")),
) -> StakeholderAssessmentResponse:
    repo = StakeholderAssessmentRepository(db)
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
    _authz=Depends(requires("stakeholder_assessment:delete", "stakeholder_assessment")),
) -> None:
    repo = StakeholderAssessmentRepository(db)
    require_deleted(await repo.delete(id), "Assessment")
