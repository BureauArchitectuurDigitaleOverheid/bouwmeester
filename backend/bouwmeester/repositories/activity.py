"""Repository for Activity log."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    ) -> list[Activity]:
        stmt = (
            select(Activity)
            .offset(skip)
            .limit(limit)
            .order_by(Activity.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
