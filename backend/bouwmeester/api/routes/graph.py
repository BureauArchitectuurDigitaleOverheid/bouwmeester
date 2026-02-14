"""API routes for graph operations."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import validate_list
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.repositories.graph import GraphRepository
from bouwmeester.schema.corpus_node import CorpusNodeResponse, NodeType
from bouwmeester.schema.edge import EdgeResponse
from bouwmeester.schema.graph import GraphViewResponse

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/search", response_model=GraphViewResponse)
async def graph_search(
    current_user: OptionalUser,
    node_types: list[NodeType] | None = Query(None),
    edge_types: list[str] | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> GraphViewResponse:
    """Return a graph view filtered by node and/or edge types.

    Uses :class:`GraphRepository.get_full_graph` to fetch all matching
    nodes and edges in a single pass rather than N+1 queries.
    """
    repo = GraphRepository(db)

    type_values = [nt.value for nt in node_types] if node_types else None
    result = await repo.get_full_graph(
        node_types=type_values,
        edge_types=edge_types,
    )

    return GraphViewResponse(
        nodes=validate_list(CorpusNodeResponse, result["nodes"]),
        edges=validate_list(EdgeResponse, result["edges"]),
    )


@router.get("/path")
async def find_path(
    current_user: OptionalUser,
    from_id: UUID = Query(...),
    to_id: UUID = Query(...),
    max_depth: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Find the shortest path between two nodes.

    Uses a recursive CTE (breadth-first search) in
    :class:`GraphRepository.find_path`.
    """
    repo = GraphRepository(db)
    path = await repo.find_path(from_id=from_id, to_id=to_id, max_depth=max_depth)

    return {
        "from_id": str(from_id),
        "to_id": str(to_id),
        "path": path,
        "length": len(path),
    }
