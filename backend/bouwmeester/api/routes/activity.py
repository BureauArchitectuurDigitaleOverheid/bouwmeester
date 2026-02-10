"""API routes for activity feed and inbox."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.schema.activity import ActivityFeedResponse, ActivityResponse
from bouwmeester.schema.inbox import InboxResponse
from bouwmeester.services.activity_service import ActivityService
from bouwmeester.services.inbox_service import InboxService

router = APIRouter(prefix="/activity", tags=["activity"])


def _activity_to_response(a) -> ActivityResponse:
    return ActivityResponse(
        id=a.id,
        event_type=a.event_type,
        actor_id=a.actor_id,
        actor_naam=a.actor.naam if a.actor else None,
        node_id=a.node_id,
        task_id=a.task_id,
        edge_id=a.edge_id,
        details=a.details,
        created_at=a.created_at,
    )


@router.get("/feed", response_model=ActivityFeedResponse)
async def get_activity_feed(
    current_user: OptionalUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    event_type: str | None = Query(None),
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> ActivityFeedResponse:
    service = ActivityService(db)
    activities = await service.get_recent(
        skip=skip, limit=limit, event_type=event_type, actor_id=actor_id
    )
    total = await service.count(event_type=event_type, actor_id=actor_id)
    return ActivityFeedResponse(
        items=[_activity_to_response(a) for a in activities],
        total=total,
    )


@router.get("/inbox", response_model=InboxResponse)
async def get_inbox(
    current_user: OptionalUser,
    person_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
) -> InboxResponse:
    service = InboxService(db)
    return await service.get_inbox(person_id)
