"""Repository for MotieImport and SuggestedEdge CRUD."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.models.motie_import import MotieImport, SuggestedEdge


class MotieImportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all(
        self,
        status: str | None = None,
        bron: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[MotieImport]:
        stmt = (
            select(MotieImport)
            .options(
                selectinload(MotieImport.suggested_edges).selectinload(
                    SuggestedEdge.target_node
                )
            )
            .order_by(MotieImport.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        if status:
            stmt = stmt.where(MotieImport.status == status)
        if bron:
            stmt = stmt.where(MotieImport.bron == bron)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, import_id: UUID) -> MotieImport | None:
        stmt = (
            select(MotieImport)
            .where(MotieImport.id == import_id)
            .options(
                selectinload(MotieImport.suggested_edges).selectinload(
                    SuggestedEdge.target_node
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_zaak_id(self, zaak_id: str) -> MotieImport | None:
        stmt = select(MotieImport).where(MotieImport.zaak_id == zaak_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_corpus_node_id(self, node_id: UUID) -> MotieImport | None:
        stmt = (
            select(MotieImport)
            .where(MotieImport.corpus_node_id == node_id)
            .options(
                selectinload(MotieImport.suggested_edges).selectinload(
                    SuggestedEdge.target_node
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> MotieImport:
        motie_import = MotieImport(**kwargs)
        self.session.add(motie_import)
        await self.session.flush()
        await self.session.refresh(motie_import)
        return motie_import

    async def update_status(
        self, import_id: UUID, status: str, **kwargs
    ) -> MotieImport | None:
        motie_import = await self.session.get(MotieImport, import_id)
        if motie_import is None:
            return None
        motie_import.status = status
        for key, value in kwargs.items():
            setattr(motie_import, key, value)
        await self.session.flush()
        # Re-fetch with eager loading to avoid lazy-load in async context
        return await self.get_by_id(import_id)

    async def get_review_queue(self) -> list[MotieImport]:
        """Get imported moties that have pending suggested edges."""
        stmt = (
            select(MotieImport)
            .where(MotieImport.status == "imported")
            .options(
                selectinload(MotieImport.suggested_edges).selectinload(
                    SuggestedEdge.target_node
                )
            )
            .order_by(MotieImport.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_pending(self) -> list[MotieImport]:
        stmt = (
            select(MotieImport)
            .where(MotieImport.status == "pending")
            .order_by(MotieImport.created_at)
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
        # Re-fetch with eager loading to avoid lazy-load in async context
        return await self.get_by_id(edge_id)
