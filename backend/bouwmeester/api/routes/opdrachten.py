"""API routes for opdrachten (assignments and subsidies)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_deleted, require_found, validate_list
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.repositories.opdracht import OpdrachtRepository
from bouwmeester.schema.opdracht import (
    OpdrachtCreate,
    OpdrachtNodeCreate,
    OpdrachtNodeResponse,
    OpdrachtResponse,
    OpdrachtUpdate,
)

router = APIRouter(prefix="/opdrachten", tags=["opdrachten"])


@router.get("", response_model=list[OpdrachtResponse])
async def list_opdrachten(
    current_user: OptionalUser,
    begrotingsjaar: int | None = None,
    type: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    instrument_id: UUID | None = None,
    opdrachtnemer_id: UUID | None = None,
    opdrachtgever_id: UUID | None = None,
    verantwoordelijke_id: UUID | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[OpdrachtResponse]:
    repo = OpdrachtRepository(db)
    items = await repo.get_all(
        skip=skip,
        limit=limit,
        begrotingsjaar=begrotingsjaar,
        type=type,
        status=status_filter,
        instrument_id=instrument_id,
        opdrachtnemer_id=opdrachtnemer_id,
        opdrachtgever_id=opdrachtgever_id,
        verantwoordelijke_id=verantwoordelijke_id,
    )
    return validate_list(OpdrachtResponse, items)


@router.post(
    "",
    response_model=OpdrachtResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_opdracht(
    data: OpdrachtCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> OpdrachtResponse:
    repo = OpdrachtRepository(db)
    opdracht = await repo.create(data)
    return OpdrachtResponse.model_validate(opdracht)


@router.get("/{id}", response_model=OpdrachtResponse)
async def get_opdracht(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> OpdrachtResponse:
    repo = OpdrachtRepository(db)
    opdracht = require_found(await repo.get(id), "Opdracht")
    return OpdrachtResponse.model_validate(opdracht)


@router.put("/{id}", response_model=OpdrachtResponse)
async def update_opdracht(
    id: UUID,
    data: OpdrachtUpdate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> OpdrachtResponse:
    repo = OpdrachtRepository(db)
    opdracht = require_found(await repo.update(id, data), "Opdracht")
    return OpdrachtResponse.model_validate(opdracht)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_opdracht(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = OpdrachtRepository(db)
    require_deleted(await repo.delete(id), "Opdracht")


# --- Node koppelingen ---


@router.post(
    "/{opdracht_id}/koppelingen",
    response_model=OpdrachtNodeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_node_koppeling(
    opdracht_id: UUID,
    data: OpdrachtNodeCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> OpdrachtNodeResponse:
    repo = OpdrachtRepository(db)
    require_found(await repo.get(opdracht_id), "Opdracht")
    link = await repo.add_node_koppeling(opdracht_id, data)
    return OpdrachtNodeResponse.model_validate(link)


@router.delete(
    "/{opdracht_id}/koppelingen/{koppeling_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_node_koppeling(
    opdracht_id: UUID,
    koppeling_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = OpdrachtRepository(db)
    require_deleted(await repo.remove_node_koppeling(koppeling_id), "Koppeling")
