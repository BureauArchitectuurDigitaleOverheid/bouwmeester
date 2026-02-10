"""API routes for edge types."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_deleted, require_found
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.repositories.edge_type import EdgeTypeRepository
from bouwmeester.schema.edge_type import EdgeTypeCreate, EdgeTypeResponse

router = APIRouter(prefix="/edge-types", tags=["edge-types"])


@router.get("", response_model=list[EdgeTypeResponse])
async def list_edge_types(
    current_user: OptionalUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[EdgeTypeResponse]:
    repo = EdgeTypeRepository(db)
    edge_types = await repo.get_all(skip=skip, limit=limit)
    return [EdgeTypeResponse.model_validate(et) for et in edge_types]


@router.post("", response_model=EdgeTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_edge_type(
    data: EdgeTypeCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> EdgeTypeResponse:
    repo = EdgeTypeRepository(db)
    edge_type = await repo.create(data)
    return EdgeTypeResponse.model_validate(edge_type)


@router.get("/{id}", response_model=EdgeTypeResponse)
async def get_edge_type(
    id: str,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> EdgeTypeResponse:
    repo = EdgeTypeRepository(db)
    edge_type = require_found(await repo.get(id), "Edge type")
    return EdgeTypeResponse.model_validate(edge_type)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_edge_type(
    id: str,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = EdgeTypeRepository(db)
    require_deleted(await repo.delete(id), "Edge type")
