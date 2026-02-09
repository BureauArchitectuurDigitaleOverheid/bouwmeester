"""API routes for edges."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_deleted, require_found
from bouwmeester.core.database import get_db
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.repositories.edge import EdgeRepository
from bouwmeester.schema.edge import EdgeCreate, EdgeResponse, EdgeUpdate, EdgeWithNodes
from bouwmeester.services.notification_service import NotificationService

router = APIRouter(prefix="/edges", tags=["edges"])


@router.get("", response_model=list[EdgeWithNodes])
async def list_edges(
    from_node_id: UUID | None = None,
    to_node_id: UUID | None = None,
    node_id: UUID | None = None,
    edge_type_id: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[EdgeWithNodes]:
    repo = EdgeRepository(db)
    edges = await repo.get_all(
        skip=skip,
        limit=limit,
        from_node_id=from_node_id,
        to_node_id=to_node_id,
        node_id=node_id,
        edge_type_id=edge_type_id,
    )
    return [EdgeWithNodes.model_validate(e) for e in edges]


@router.post("", response_model=EdgeResponse, status_code=status.HTTP_201_CREATED)
async def create_edge(
    data: EdgeCreate,
    db: AsyncSession = Depends(get_db),
) -> EdgeResponse:
    repo = EdgeRepository(db)
    try:
        edge = await repo.create(data)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Deze verbinding bestaat al.",
        )

    # Notify stakeholders of both nodes
    from_node = await db.get(CorpusNode, data.from_node_id)
    to_node = await db.get(CorpusNode, data.to_node_id)
    if from_node and to_node:
        notif_svc = NotificationService(db)
        await notif_svc.notify_edge_created(from_node, to_node, edge.id)

    return EdgeResponse.model_validate(edge)


@router.get("/{id}", response_model=EdgeWithNodes)
async def get_edge(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> EdgeWithNodes:
    repo = EdgeRepository(db)
    edge = require_found(await repo.get(id), "Edge")
    return EdgeWithNodes.model_validate(edge)


@router.put("/{id}", response_model=EdgeResponse)
async def update_edge(
    id: UUID,
    data: EdgeUpdate,
    db: AsyncSession = Depends(get_db),
) -> EdgeResponse:
    repo = EdgeRepository(db)
    edge = require_found(await repo.update(id, data), "Edge")
    return EdgeResponse.model_validate(edge)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_edge(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = EdgeRepository(db)
    require_deleted(await repo.delete(id), "Edge")
