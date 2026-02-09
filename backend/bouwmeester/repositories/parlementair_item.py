"""Repository for ParlementairItem and SuggestedEdge CRUD."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.models.parlementair_item import ParlementairItem, SuggestedEdge


class ParlementairItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all(
        self,
        status: str | None = None,
        bron: str | None = None,
        item_type: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ParlementairItem]:
        stmt = (
            select(ParlementairItem)
            .options(
                selectinload(ParlementairItem.suggested_edges).selectinload(
                    SuggestedEdge.target_node
                )
            )
            .order_by(ParlementairItem.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        if status:
            stmt = stmt.where(ParlementairItem.status == status)
        if bron:
            stmt = stmt.where(ParlementairItem.bron == bron)
        if item_type:
            stmt = stmt.where(ParlementairItem.type == item_type)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, import_id: UUID) -> ParlementairItem | None:
        stmt = (
            select(ParlementairItem)
            .where(ParlementairItem.id == import_id)
            .options(
                selectinload(ParlementairItem.suggested_edges).selectinload(
                    SuggestedEdge.target_node
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_zaak_id(self, zaak_id: str) -> ParlementairItem | None:
        stmt = select(ParlementairItem).where(ParlementairItem.zaak_id == zaak_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> ParlementairItem:
        item = ParlementairItem(**kwargs)
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def update_status(
        self, import_id: UUID, status: str, **kwargs
    ) -> ParlementairItem | None:
        item = await self.session.get(ParlementairItem, import_id)
        if item is None:
            return None
        item.status = status
        for key, value in kwargs.items():
            setattr(item, key, value)
        await self.session.flush()
        return await self.get_by_id(import_id)

    async def get_review_queue(
        self,
        item_type: str | None = None,
    ) -> list[ParlementairItem]:
        """Get imported items that have pending suggested edges."""
        stmt = (
            select(ParlementairItem)
            .where(ParlementairItem.status == "imported")
            .options(
                selectinload(ParlementairItem.suggested_edges).selectinload(
                    SuggestedEdge.target_node
                )
            )
            .order_by(ParlementairItem.created_at.desc())
        )
        if item_type:
            stmt = stmt.where(ParlementairItem.type == item_type)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_pending(self) -> list[ParlementairItem]:
        stmt = (
            select(ParlementairItem)
            .where(ParlementairItem.status == "pending")
            .order_by(ParlementairItem.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class SuggestedEdgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, edge_id: UUID) -> SuggestedEdge | None:
        stmt = (
            select(SuggestedEdge)
            .where(SuggestedEdge.id == edge_id)
            .options(selectinload(SuggestedEdge.target_node))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> SuggestedEdge:
        suggested_edge = SuggestedEdge(**kwargs)
        self.session.add(suggested_edge)
        await self.session.flush()
        await self.session.refresh(suggested_edge)
        return suggested_edge

    async def update_status(
        self, edge_id: UUID, status: str, **kwargs
    ) -> SuggestedEdge | None:
        suggested_edge = await self.session.get(SuggestedEdge, edge_id)
        if suggested_edge is None:
            return None
        suggested_edge.status = status
        for key, value in kwargs.items():
            setattr(suggested_edge, key, value)
        await self.session.flush()
        return await self.get_by_id(edge_id)
