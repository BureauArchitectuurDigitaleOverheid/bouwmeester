"""Repository for NodeStakeholder operations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bouwmeester.models.node_stakeholder import NodeStakeholder
from bouwmeester.repositories.base import BaseRepository


class NodeStakeholderRepository(BaseRepository[NodeStakeholder]):
    model = NodeStakeholder

    async def get_by_node(self, node_id: UUID) -> list[NodeStakeholder]:
        stmt = (
            select(NodeStakeholder)
            .where(NodeStakeholder.node_id == node_id)
            .options(selectinload(NodeStakeholder.person))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_with_person(
        self,
        stakeholder_id: UUID,
        node_id: UUID,
    ) -> NodeStakeholder | None:
        stmt = (
            select(NodeStakeholder)
            .where(
                NodeStakeholder.id == stakeholder_id,
                NodeStakeholder.node_id == node_id,
            )
            .options(selectinload(NodeStakeholder.person))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_stakeholder(
        self,
        node_id: UUID,
        person_id: UUID,
        rol: str,
    ) -> NodeStakeholder:
        stakeholder = NodeStakeholder(
            node_id=node_id,
            person_id=person_id,
            rol=rol,
        )
        self.session.add(stakeholder)
        await self.session.flush()
        # Reload with person
        stmt = (
            select(NodeStakeholder)
            .where(NodeStakeholder.id == stakeholder.id)
            .options(selectinload(NodeStakeholder.person))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
