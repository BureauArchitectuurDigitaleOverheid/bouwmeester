"""API routes for externe organisaties."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_deleted, require_found
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.repositories.externe_organisatie import ExterneOrganisatieRepository
from bouwmeester.schema.externe_organisatie import (
    ExterneOrganisatieCreate,
    ExterneOrganisatieResponse,
    ExterneOrganisatieUpdate,
)

router = APIRouter(prefix="/externe-organisaties", tags=["externe-organisaties"])


@router.get("", response_model=list[ExterneOrganisatieResponse])
async def list_externe_organisaties(
    current_user: OptionalUser,
    type: str | None = None,
    search: str | None = Query(None, max_length=200),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[ExterneOrganisatieResponse]:
    repo = ExterneOrganisatieRepository(db)
    items = await repo.get_all(skip=skip, limit=limit, type=type, search=search)
    return [ExterneOrganisatieResponse.model_validate(o) for o in items]


@router.post(
    "",
    response_model=ExterneOrganisatieResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_externe_organisatie(
    data: ExterneOrganisatieCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> ExterneOrganisatieResponse:
    repo = ExterneOrganisatieRepository(db)
    org = await repo.create(data)
    return ExterneOrganisatieResponse.model_validate(org)


@router.get("/{id}", response_model=ExterneOrganisatieResponse)
async def get_externe_organisatie(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> ExterneOrganisatieResponse:
    repo = ExterneOrganisatieRepository(db)
    org = require_found(await repo.get_by_id(id), "Externe organisatie")
    return ExterneOrganisatieResponse.model_validate(org)


@router.put("/{id}", response_model=ExterneOrganisatieResponse)
async def update_externe_organisatie(
    id: UUID,
    data: ExterneOrganisatieUpdate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> ExterneOrganisatieResponse:
    repo = ExterneOrganisatieRepository(db)
    org = require_found(await repo.update(id, data), "Externe organisatie")
    return ExterneOrganisatieResponse.model_validate(org)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_externe_organisatie(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = ExterneOrganisatieRepository(db)
    require_deleted(await repo.delete(id), "Externe organisatie")
