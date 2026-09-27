"""API routes for graph operations."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import validate_list
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.initiatief_context import (
    InitiatiefContext,
    get_initiatief_context,
)
from bouwmeester.core.org_context import OrgContext, get_org_context
from bouwmeester.core.permissions import PermissionContext, get_permission_context
from bouwmeester.repositories.graph import GraphRepository
from bouwmeester.schema.community_graph import CommunityGraphResponse
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
    org_ctx: OrgContext = Depends(get_org_context),
) -> GraphViewResponse:
    """Return the visible graph, filtered by node and/or edge types."""
    repo = GraphRepository(db)

    type_values = [nt.value for nt in node_types] if node_types else None
    result = await repo.get_full_graph(
        org_ctx=org_ctx,
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
    org_ctx: OrgContext = Depends(get_org_context),
) -> dict:
    """Find the shortest path between two nodes, through visible nodes only."""
    repo = GraphRepository(db)
    path = await repo.find_path(from_id, to_id, org_ctx=org_ctx, max_depth=max_depth)

    return {
        "from_id": str(from_id),
        "to_id": str(to_id),
        "path": path,
        "length": len(path),
    }


@router.get("/community", response_model=CommunityGraphResponse)
async def get_community_graph(
    current_user: OptionalUser,
    org_ctx: OrgContext = Depends(get_org_context),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
    initiatief_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> CommunityGraphResponse:
    """Return a community graph of leads, people, organisations and corpus nodes.

    Builds a unified graph starting from leads (filtered by the caller's
    initiatief context for visibility, and optionally narrowed to a single
    ``initiatief_id``) and transitively includes all related persons,
    external organisations, samenwerkingsverbanden and corpus nodes.  People
    only for whoever holds ``people:read``, as ``GET /people`` asks, and
    samenwerkingsverbanden only with ``samenwerkingsverband:read``.
    """
    repo = GraphRepository(db)
    return await repo.get_community_graph(
        org_ctx=org_ctx,
        init_ctx=init_ctx,
        initiatief_id=initiatief_id,
        include_people=perm_ctx.has_permission("people:read"),
        include_samenwerkingsverbanden=perm_ctx.has_permission(
            "samenwerkingsverband:read"
        ),
    )
