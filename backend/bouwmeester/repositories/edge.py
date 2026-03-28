"""Repository for Edge CRUD."""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from bouwmeester.core.org_context import OrgContext, apply_org_filter
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge
from bouwmeester.repositories.base import BaseRepository


def _visible_node_ids(org_ctx: OrgContext | None):
    """Subquery returning CorpusNode IDs visible to the given org context."""
    stmt = select(CorpusNode.id)
    return apply_org_filter(
        stmt, CorpusNode.organisatie_eenheid_id, org_ctx
    ).scalar_subquery()


class EdgeRepository(BaseRepository[Edge]):
    model = Edge

    async def get(self, id: UUID, org_ctx: OrgContext | None = None) -> Edge | None:
        stmt = (
            select(Edge)
            .where(Edge.id == id)
            .options(
                selectinload(Edge.from_node),
                selectinload(Edge.to_node),
            )
        )
        if org_ctx is not None and not org_ctx.is_admin:
            visible = _visible_node_ids(org_ctx)
            stmt = stmt.where(
                Edge.from_node_id.in_(visible),
                Edge.to_node_id.in_(visible),
            )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        from_node_id: UUID | None = None,
        to_node_id: UUID | None = None,
        node_id: UUID | None = None,
        edge_type_id: str | None = None,
        org_ctx: OrgContext | None = None,
    ) -> list[Edge]:
        stmt = (
            select(Edge)
            .options(selectinload(Edge.from_node), selectinload(Edge.to_node))
            .offset(skip)
            .limit(limit)
        )
        if node_id is not None:
            stmt = stmt.where(
                or_(Edge.from_node_id == node_id, Edge.to_node_id == node_id)
            )
        if from_node_id is not None:
            stmt = stmt.where(Edge.from_node_id == from_node_id)
        if to_node_id is not None:
            stmt = stmt.where(Edge.to_node_id == to_node_id)
        if edge_type_id is not None:
            stmt = stmt.where(Edge.edge_type_id == edge_type_id)
        if org_ctx is not None and not org_ctx.is_admin:
            visible = _visible_node_ids(org_ctx)
            stmt = stmt.where(
                Edge.from_node_id.in_(visible),
                Edge.to_node_id.in_(visible),
            )
        stmt = stmt.order_by(Edge.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
