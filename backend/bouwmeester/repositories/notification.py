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
            .where(
                Notification.parent_id == parent_id,
                Notification.type != "emoji_reaction",
            )
            .order_by(Notification.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_replies(self, parent_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.parent_id == parent_id,
                Notification.type != "emoji_reaction",
            )
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
            .where(
                Notification.parent_id.in_(parent_ids),
                Notification.type != "emoji_reaction",
            )
            .group_by(Notification.parent_id)
        )
        result = await self.session.execute(stmt)
        return {row.parent_id: row.cnt for row in result.all()}

    async def last_activity_batch(
        self, parent_ids: list[UUID]
    ) -> dict[UUID, tuple[datetime, str | None, str]]:
        """Get latest reply timestamp, message, and type per parent.

        Uses PostgreSQL DISTINCT ON to guarantee exactly one row per
        parent_id, even when two replies share the same created_at.
        Includes emoji reactions so the inbox preview stays current.
        """
        if not parent_ids:
            return {}

        stmt = (
            select(
                Notification.parent_id,
                Notification.created_at,
                Notification.message,
                Notification.type,
            )
            .where(Notification.parent_id.in_(parent_ids))
            .order_by(
                Notification.parent_id,
                Notification.created_at.desc(),
                Notification.id.desc(),
            )
            .distinct(Notification.parent_id)
        )
        result = await self.session.execute(stmt)
        return {
            row.parent_id: (row.created_at, row.message, row.type)
            for row in result.all()
        }

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

    async def find_existing_reaction(
        self, message_id: UUID, sender_id: UUID, emoji: str
    ) -> Notification | None:
        """Find an existing emoji reaction for toggle detection."""
        stmt = select(Notification).where(
            Notification.parent_id == message_id,
            Notification.sender_id == sender_id,
            Notification.type == "emoji_reaction",
            Notification.message == emoji,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_reactions_for_messages(
        self, message_ids: list[UUID]
    ) -> dict[UUID, list[Notification]]:
        """Fetch emoji_reaction notifications parented to these messages."""
        if not message_ids:
            return {}
        stmt = (
            select(Notification)
            .where(
                Notification.parent_id.in_(message_ids),
                Notification.type == "emoji_reaction",
            )
            .order_by(Notification.created_at.asc())
        )
        result = await self.session.execute(stmt)
        reactions: dict[UUID, list[Notification]] = {}
        for r in result.scalars().all():
            reactions.setdefault(r.parent_id, []).append(r)
        return reactions

    async def delete(self, notification: Notification) -> None:
        """Delete a notification."""
        await self.session.delete(notification)
        await self.session.flush()

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
