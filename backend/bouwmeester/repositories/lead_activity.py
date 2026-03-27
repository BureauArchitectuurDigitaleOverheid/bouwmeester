"""Repository for LeadActivity CRUD and queries."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bouwmeester.models.lead_activity import LeadActivity
from bouwmeester.repositories.base import BaseRepository
from bouwmeester.schema.lead import LeadActivityCreate


class LeadActivityRepository(BaseRepository[LeadActivity]):
    model = LeadActivity

    async def create(
        self,
        lead_id: UUID,
        data: LeadActivityCreate,
        author_id: UUID | None = None,
    ) -> LeadActivity:
        activity = LeadActivity(
            lead_id=lead_id,
            author_id=author_id,
            content=data.content,
            activity_type=data.activity_type,
        )
        self.session.add(activity)
        await self.session.flush()
        await self.session.refresh(activity, attribute_names=["author"])
        return activity

    async def get_by_lead(self, lead_id: UUID) -> list[LeadActivity]:
        stmt = (
            select(LeadActivity)
            .where(LeadActivity.lead_id == lead_id)
            .options(selectinload(LeadActivity.author))
            .order_by(LeadActivity.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
