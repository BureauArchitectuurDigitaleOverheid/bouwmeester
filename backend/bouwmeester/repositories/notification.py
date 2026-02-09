"""Repository for Notification CRUD."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update

from bouwmeester.models.notification import Notification
from bouwmeester.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    model = Notification

    async def get_by_person(
        self,
        person_id: UUID,
        unread_only: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Notification]:
        stmt = (
            select(Notification)
            .where(
                Notification.person_id == person_id,
                Notification.parent_id.is_(None),
            )
            .offset(skip)
            .limit(limit)
            .order_by(Notification.created_at.desc())
        )
        if unread_only:
            stmt = stmt.where(Notification.is_read == False)  # noqa: E712
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_replies(self, parent_id: UUID) -> list[Notification]:
        stmt = (
            select(Notification)
            .where(Notification.parent_id == parent_id)
            .order_by(Notification.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_replies(self, parent_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Notification)
            .where(Notification.parent_id == parent_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def count_replies_batch(self, parent_ids: list[UUID]) -> dict[UUID, int]:
        """Count replies for multiple parent notifications in a single query."""
        if not parent_ids:
            return {}
        stmt = (
            select(
                Notification.parent_id,
                func.count().label("cnt"),
            )
            .where(Notification.parent_id.in_(parent_ids))
            .group_by(Notification.parent_id)
        )
        result = await self.session.execute(stmt)
        return {row.parent_id: row.cnt for row in result.all()}

    async def last_activity_batch(
        self, parent_ids: list[UUID]
    ) -> dict[UUID, tuple[datetime, str | None]]:
        """Get latest reply timestamp and message per parent."""
        if not parent_ids:
            return {}

        from sqlalchemy import and_

        # Subquery: max created_at per parent_id
        max_sub = (
            select(
                Notification.parent_id.label("pid"),
                func.max(Notification.created_at).label("max_at"),
            )
            .where(Notification.parent_id.in_(parent_ids))
            .group_by(Notification.parent_id)
            .subquery()
        )

        # Join back to get the message of the latest reply
        stmt = select(
            Notification.parent_id,
            Notification.created_at,
            Notification.message,
        ).join(
            max_sub,
            and_(
                Notification.parent_id == max_sub.c.pid,
                Notification.created_at == max_sub.c.max_at,
            ),
        )
        result = await self.session.execute(stmt)
        return {row.parent_id: (row.created_at, row.message) for row in result.all()}

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
        """Count unread root notifications (excludes replies to match list view)."""
        stmt = (
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.person_id == person_id,
                Notification.parent_id.is_(None),
                Notification.is_read == False,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_other_root(
        self, thread_id: UUID, person_id: UUID
    ) -> Notification | None:
        """Find the other party's root notification in a DM thread."""
        stmt = select(Notification).where(
            Notification.thread_id == thread_id,
            Notification.parent_id.is_(None),
            Notification.person_id != person_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
