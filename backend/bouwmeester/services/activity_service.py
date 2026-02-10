"""Service layer for Activity logging."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.activity import Activity
from bouwmeester.repositories.activity import ActivityRepository


def resolve_actor_id(current_user: Any, actor_id: UUID | None) -> UUID | None:
    """Prefer authenticated user's ID; fall back to query param for dev mode."""
    if current_user is not None:
        return current_user.id
    return actor_id


def resolve_actor_naam(current_user: Any) -> str | None:
    """Return the authenticated user's name, or None."""
    if current_user is not None:
        return current_user.naam
    return None


class ActivityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ActivityRepository(session)

    async def log_event(
        self,
        event_type: str,
        actor_id: UUID | None = None,
        actor_naam: str | None = None,
        node_id: UUID | None = None,
        task_id: UUID | None = None,
        edge_id: UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> Activity:
        if actor_naam:
            if details is None:
                details = {}
            else:
                details = dict(details)
            details["actor_naam"] = actor_naam
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
