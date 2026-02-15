"""API routes for edge types."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_deleted, require_found
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.repositories.edge_schema_rule import EdgeSchemaRuleRepository
from bouwmeester.repositories.edge_type import EdgeTypeRepository
from bouwmeester.schema.edge_schema_rule import ValidEdgeTypesResponse
from bouwmeester.schema.edge_type import EdgeTypeCreate, EdgeTypeResponse

router = APIRouter(prefix="/edge-types", tags=["edge-types"])


@router.get("", response_model=list[EdgeTypeResponse])
async def list_edge_types(
    current_user: OptionalUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[EdgeTypeResponse]:
    """List all edge type definitions (e.g. draagt_bij_aan, implementeert)."""
    repo = EdgeTypeRepository(db)
    edge_types = await repo.get_all(skip=skip, limit=limit)
    return [EdgeTypeResponse.model_validate(et) for et in edge_types]


@router.get("/valid", response_model=ValidEdgeTypesResponse)
async def get_valid_edge_types(
    current_user: OptionalUser,
    from_node_type: str | None = Query(None),
    to_node_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> ValidEdgeTypesResponse:
    """Return valid edge type IDs for a given node type pair.

    If no schema rules exist, returns schema_active=false and an empty list.
    """
    repo = EdgeSchemaRuleRepository(db)
    has_rules = await repo.has_any_rules()
    if not has_rules:
        return ValidEdgeTypesResponse(edge_type_ids=[], schema_active=False)
    ids = await repo.get_valid_edge_type_ids(from_node_type, to_node_type)
    return ValidEdgeTypesResponse(edge_type_ids=sorted(ids), schema_active=True)


@router.post("", response_model=EdgeTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_edge_type(
    data: EdgeTypeCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> EdgeTypeResponse:
    """Create a new edge type definition."""
    repo = EdgeTypeRepository(db)
    edge_type = await repo.create(data)
    return EdgeTypeResponse.model_validate(edge_type)


@router.get("/{id}", response_model=EdgeTypeResponse)
async def get_edge_type(
    id: str,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> EdgeTypeResponse:
    """Get a single edge type by its string ID."""
    repo = EdgeTypeRepository(db)
    edge_type = require_found(await repo.get(id), "Edge type")
    return EdgeTypeResponse.model_validate(edge_type)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_edge_type(
    id: str,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an edge type permanently."""
    repo = EdgeTypeRepository(db)
    require_deleted(await repo.delete(id), "Edge type")
