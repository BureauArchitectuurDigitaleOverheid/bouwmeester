"""API routes for corpus nodes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import get_db
from bouwmeester.repositories.task import TaskRepository
from bouwmeester.schema.corpus_node import (
    CorpusNodeCreate,
    CorpusNodeResponse,
    CorpusNodeUpdate,
    CorpusNodeWithEdges,
    NodeType,
)
from bouwmeester.schema.edge import EdgeResponse
from bouwmeester.schema.graph import (
    GraphNeighborsResponse,
    GraphViewResponse,
    NeighborEntry,
)
from bouwmeester.schema.person import PersonResponse
from bouwmeester.schema.task import TaskResponse
from bouwmeester.services.node_service import NodeService

# Resolve forward reference to EdgeResponse in CorpusNodeWithEdges.
CorpusNodeWithEdges.model_rebuild()

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.get("", response_model=list[CorpusNodeResponse])
async def list_nodes(
    node_type: NodeType | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[CorpusNodeResponse]:
    service = NodeService(db)
    node_type_str = node_type.value if node_type else None
    nodes = await service.get_all(skip=skip, limit=limit, node_type=node_type_str)
    return [CorpusNodeResponse.model_validate(n) for n in nodes]


@router.post(
    "", response_model=CorpusNodeResponse, status_code=status.HTTP_201_CREATED
)
async def create_node(
    data: CorpusNodeCreate,
    db: AsyncSession = Depends(get_db),
) -> CorpusNodeResponse:
    service = NodeService(db)
    node = await service.create(data)
    return CorpusNodeResponse.model_validate(node)


@router.get("/{id}", response_model=CorpusNodeWithEdges)
async def get_node(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> CorpusNodeWithEdges:
    service = NodeService(db)
    node = await service.get(id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return CorpusNodeWithEdges(
        id=node.id,
        title=node.title,
        description=node.description,
        node_type=node.node_type,
        status=node.status,
        created_at=node.created_at,
        updated_at=node.updated_at,
        edges_from=[EdgeResponse.model_validate(e) for e in node.edges_from],
        edges_to=[EdgeResponse.model_validate(e) for e in node.edges_to],
    )


@router.put("/{id}", response_model=CorpusNodeResponse)
async def update_node(
    id: UUID,
    data: CorpusNodeUpdate,
    db: AsyncSession = Depends(get_db),
) -> CorpusNodeResponse:
    service = NodeService(db)
    node = await service.update(id, data)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return CorpusNodeResponse.model_validate(node)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    service = NodeService(db)
    deleted = await service.delete(id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Node not found")


@router.get("/{id}/neighbors", response_model=GraphNeighborsResponse)
async def get_neighbors(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> GraphNeighborsResponse:
    service = NodeService(db)
    result = await service.get_neighbors(id)
    if result["node"] is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return GraphNeighborsResponse(
        node=CorpusNodeResponse.model_validate(result["node"]),
        neighbors=[
            NeighborEntry(
                node=CorpusNodeResponse.model_validate(n["node"]),
                edge=EdgeResponse.model_validate(n["edge"]),
            )
            for n in result["neighbors"]
        ],
    )


@router.get("/{id}/graph", response_model=GraphViewResponse)
async def get_graph(
    id: UUID,
    depth: int = Query(2, ge=1, le=5),
    db: AsyncSession = Depends(get_db),
) -> GraphViewResponse:
    service = NodeService(db)
    result = await service.get_graph(id, depth=depth)
    return GraphViewResponse(
        nodes=[CorpusNodeResponse.model_validate(n) for n in result["nodes"]],
        edges=[EdgeResponse.model_validate(e) for e in result["edges"]],
    )


@router.get("/{id}/tasks", response_model=list[TaskResponse])
async def get_node_tasks(
    id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[TaskResponse]:
    # Verify node exists
    service = NodeService(db)
    node = await service.get(id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")

    task_repo = TaskRepository(db)
    tasks = await task_repo.get_by_node(id, skip=skip, limit=limit)
    return [TaskResponse.model_validate(t) for t in tasks]


@router.get("/{id}/stakeholders", response_model=list[PersonResponse])
async def get_node_stakeholders(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[PersonResponse]:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from bouwmeester.models.node_stakeholder import NodeStakeholder

    # Verify node exists
    service = NodeService(db)
    node = await service.get(id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")

    stmt = (
        select(NodeStakeholder)
        .where(NodeStakeholder.node_id == id)
        .options(selectinload(NodeStakeholder.person))
    )
    result = await db.execute(stmt)
    stakeholders = result.scalars().all()
    return [PersonResponse.model_validate(s.person) for s in stakeholders]
