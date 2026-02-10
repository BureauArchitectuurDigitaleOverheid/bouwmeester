"""Service layer for Activity logging."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.activity import Activity
from bouwmeester.repositories.activity import ActivityRepository


class ActivityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ActivityRepository(session)

    async def log_event(
        self,
        event_type: str,
        actor_id: UUID | None = None,
        node_id: UUID | None = None,
        task_id: UUID | None = None,
        edge_id: UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> Activity:
        return await self.repo.create(
            event_type=event_type,
            actor_id=actor_id,
            node_id=node_id,
            task_id=task_id,
            edge_id=edge_id,
            details=details,
        )

    async def get_recent(
        self,
        skip: int = 0,
        limit: int = 50,
        event_type: str | None = None,
        actor_id: UUID | None = None,
    ) -> list[Activity]:
        return await self.repo.get_recent(
            skip=skip, limit=limit, event_type=event_type, actor_id=actor_id
        )

    async def count(
        self,
        event_type: str | None = None,
        actor_id: UUID | None = None,
    ) -> int:
        return await self.repo.count(event_type=event_type, actor_id=actor_id)

    async def get_by_node(
        self,
        node_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Activity]:
        return await self.repo.get_by_node(node_id, skip=skip, limit=limit)

    async def get_by_person(
        self,
        person_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Activity]:
        return await self.repo.get_by_person(person_id, skip=skip, limit=limit)
