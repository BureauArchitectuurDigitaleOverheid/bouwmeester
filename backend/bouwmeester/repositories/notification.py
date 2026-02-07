"""Repository for Notification CRUD."""

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.notification import Notification
from bouwmeester.schema.notification import NotificationCreate


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_person(
        self,
        person_id: UUID,
        unread_only: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Notification]:
        stmt = (
            select(Notification)
            .where(Notification.person_id == person_id)
            .offset(skip)
            .limit(limit)
            .order_by(Notification.created_at.desc())
        )
        if unread_only:
            stmt = stmt.where(Notification.is_read == False)  # noqa: E712
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: NotificationCreate) -> Notification:
        notification = Notification(**data.model_dump())
        self.session.add(notification)
        await self.session.flush()
        await self.session.refresh(notification)
        return notification

    async def mark_read(self, notification_id: UUID) -> Notification | None:
        notification = await self.session.get(Notification, notification_id)
        if notification is None:
            return None
        notification.is_read = True
        await self.session.flush()
        await self.session.refresh(notification)
        return notification

    async def mark_all_read(self, person_id: UUID) -> int:
        stmt = (
            update(Notification)
            .where(
                Notification.person_id == person_id,
                Notification.is_read == False,  # noqa: E712
            )
            .values(is_read=True)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def count_unread(self, person_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.person_id == person_id,
                Notification.is_read == False,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
