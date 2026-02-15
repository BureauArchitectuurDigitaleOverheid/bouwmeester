"""Repository for EdgeSchemaRule CRUD and queries."""

from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.edge_schema_rule import EdgeSchemaRule


class EdgeSchemaRuleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all(self) -> list[EdgeSchemaRule]:
        stmt = select(EdgeSchemaRule).order_by(
            EdgeSchemaRule.from_node_type,
            EdgeSchemaRule.to_node_type,
            EdgeSchemaRule.edge_type_id,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def has_any_rules(self) -> bool:
        stmt = select(EdgeSchemaRule.id).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_valid_edge_type_ids(
        self,
        from_node_type: str | None = None,
        to_node_type: str | None = None,
    ) -> list[str]:
        stmt = select(EdgeSchemaRule.edge_type_id).distinct()
        if from_node_type is not None:
            stmt = stmt.where(EdgeSchemaRule.from_node_type == from_node_type)
        if to_node_type is not None:
            stmt = stmt.where(EdgeSchemaRule.to_node_type == to_node_type)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def is_valid_combination(
        self,
        from_node_type: str,
        to_node_type: str,
        edge_type_id: str,
    ) -> bool:
        stmt = select(EdgeSchemaRule.id).where(
            EdgeSchemaRule.from_node_type == from_node_type,
            EdgeSchemaRule.to_node_type == to_node_type,
            EdgeSchemaRule.edge_type_id == edge_type_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def create(self, data: BaseModel) -> EdgeSchemaRule:
        obj = EdgeSchemaRule(**data.model_dump())
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def delete(self, id: UUID) -> bool:
        obj = await self.session.get(EdgeSchemaRule, id)
        if obj is None:
            return False
        await self.session.delete(obj)
        await self.session.flush()
        return True
