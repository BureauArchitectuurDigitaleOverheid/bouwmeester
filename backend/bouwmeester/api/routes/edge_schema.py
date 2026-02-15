"""API routes for edge schema rules (admin CRUD)."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_deleted
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.repositories.edge_schema_rule import EdgeSchemaRuleRepository
from bouwmeester.schema.edge_schema_rule import (
    EdgeSchemaRuleCreate,
    EdgeSchemaRuleResponse,
)

router = APIRouter(prefix="/edge-schema-rules", tags=["edge-schema-rules"])


@router.get("", response_model=list[EdgeSchemaRuleResponse])
async def list_rules(
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> list[EdgeSchemaRuleResponse]:
    """List all edge schema rules."""
    repo = EdgeSchemaRuleRepository(db)
    rules = await repo.get_all()
    return [EdgeSchemaRuleResponse.model_validate(r) for r in rules]


@router.post(
    "", response_model=EdgeSchemaRuleResponse, status_code=status.HTTP_201_CREATED
)
async def create_rule(
    data: EdgeSchemaRuleCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> EdgeSchemaRuleResponse:
    """Create a new edge schema rule."""
    repo = EdgeSchemaRuleRepository(db)
    rule = await repo.create(data)
    return EdgeSchemaRuleResponse.model_validate(rule)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an edge schema rule."""
    repo = EdgeSchemaRuleRepository(db)
    require_deleted(await repo.delete(id), "Edge schema rule")
