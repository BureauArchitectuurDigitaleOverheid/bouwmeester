"""Repository for Mention CRUD."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.mention import Mention
from bouwmeester.schema.mention import MentionCreate


class MentionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: MentionCreate) -> Mention:
        mention = Mention(**data.model_dump())
        self.session.add(mention)
        await self.session.flush()
        return mention

    async def create_many(self, items: list[MentionCreate]) -> list[Mention]:
        mentions = [Mention(**d.model_dump()) for d in items]
        self.session.add_all(mentions)
        await self.session.flush()
        return mentions

    async def delete_by_source(self, source_type: str, source_id: UUID) -> int:
        stmt = delete(Mention).where(
            Mention.source_type == source_type,
            Mention.source_id == source_id,
        )
        result = await self.session.execute(stmt)
        return result.rowcount

    async def get_by_target(
        self, target_id: UUID, allowed_source_types: list[str] | None = None
    ) -> list[Mention]:
        stmt = (
            select(Mention)
            .where(Mention.target_id == target_id)
            .order_by(Mention.created_at.desc())
        )
        if allowed_source_types:
            stmt = stmt.where(Mention.source_type.in_(allowed_source_types))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_source(self, source_type: str, source_id: UUID) -> list[Mention]:
        stmt = (
            select(Mention)
            .where(
                Mention.source_type == source_type,
                Mention.source_id == source_id,
            )
            .order_by(Mention.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
