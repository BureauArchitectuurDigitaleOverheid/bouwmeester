"""API routes for edges."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import get_db
from bouwmeester.repositories.edge import EdgeRepository
from bouwmeester.schema.corpus_node import CorpusNodeResponse
from bouwmeester.schema.edge import EdgeCreate, EdgeResponse, EdgeUpdate, EdgeWithNodes

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
    return [
        EdgeWithNodes(
            id=e.id,
            from_node_id=e.from_node_id,
            to_node_id=e.to_node_id,
            edge_type_id=e.edge_type_id,
            weight=e.weight,
            description=e.description,
            created_at=e.created_at,
            from_node=CorpusNodeResponse.model_validate(e.from_node),
            to_node=CorpusNodeResponse.model_validate(e.to_node),
        )
        for e in edges
    ]


@router.post("", response_model=EdgeResponse, status_code=status.HTTP_201_CREATED)
async def create_edge(
    data: EdgeCreate,
    db: AsyncSession = Depends(get_db),
) -> EdgeResponse:
    repo = EdgeRepository(db)
    edge = await repo.create(data)
    return EdgeResponse.model_validate(edge)


@router.get("/{id}", response_model=EdgeWithNodes)
async def get_edge(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> EdgeWithNodes:
    repo = EdgeRepository(db)
    edge = await repo.get(id)
    if edge is None:
        raise HTTPException(status_code=404, detail="Edge not found")
    return EdgeWithNodes(
        id=edge.id,
        from_node_id=edge.from_node_id,
        to_node_id=edge.to_node_id,
        edge_type_id=edge.edge_type_id,
        weight=edge.weight,
        description=edge.description,
        created_at=edge.created_at,
        from_node=CorpusNodeResponse.model_validate(edge.from_node),
        to_node=CorpusNodeResponse.model_validate(edge.to_node),
    )


@router.put("/{id}", response_model=EdgeResponse)
async def update_edge(
    id: UUID,
    data: EdgeUpdate,
    db: AsyncSession = Depends(get_db),
) -> EdgeResponse:
    repo = EdgeRepository(db)
    edge = await repo.update(id, data)
    if edge is None:
        raise HTTPException(status_code=404, detail="Edge not found")
    return EdgeResponse.model_validate(edge)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_edge(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = EdgeRepository(db)
    deleted = await repo.delete(id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Edge not found")
