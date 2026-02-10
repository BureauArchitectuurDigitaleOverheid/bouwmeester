"""Repository for Activity log."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.models.activity import Activity


class ActivityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        event_type: str,
        actor_id: UUID | None = None,
        node_id: UUID | None = None,
        task_id: UUID | None = None,
        edge_id: UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> Activity:
        activity = Activity(
            event_type=event_type,
            actor_id=actor_id,
            node_id=node_id,
            task_id=task_id,
            edge_id=edge_id,
            details=details,
        )
        self.session.add(activity)
        await self.session.flush()
        await self.session.refresh(activity)
        return activity

    async def get_by_node(
        self,
        node_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Activity]:
        stmt = (
            select(Activity)
            .where(Activity.node_id == node_id)
            .options(selectinload(Activity.actor))
            .offset(skip)
            .limit(limit)
            .order_by(Activity.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_person(
        self,
        person_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Activity]:
        stmt = (
            select(Activity)
            .where(Activity.actor_id == person_id)
            .options(selectinload(Activity.actor))
            .offset(skip)
            .limit(limit)
            .order_by(Activity.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent(
        self,
        skip: int = 0,
        limit: int = 50,
        event_type: str | None = None,
        actor_id: UUID | None = None,
    ) -> list[Activity]:
        stmt = (
            select(Activity)
            .options(selectinload(Activity.actor))
            .order_by(Activity.created_at.desc())
        )
        # NOTE: For large tables, consider adding a text_pattern_ops index on event_type
        if event_type:
            stmt = stmt.where(Activity.event_type.startswith(event_type))
        if actor_id:
            stmt = stmt.where(Activity.actor_id == actor_id)
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(
        self,
        event_type: str | None = None,
        actor_id: UUID | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(Activity)
        if event_type:
            stmt = stmt.where(Activity.event_type.startswith(event_type))
        if actor_id:
            stmt = stmt.where(Activity.actor_id == actor_id)
        result = await self.session.execute(stmt)
        return result.scalar() or 0
