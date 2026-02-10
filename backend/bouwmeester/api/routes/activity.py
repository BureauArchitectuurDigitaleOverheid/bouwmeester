"""API routes for activity feed and inbox."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.schema.activity import ActivityResponse
from bouwmeester.schema.inbox import InboxResponse
from bouwmeester.services.activity_service import ActivityService
from bouwmeester.services.inbox_service import InboxService

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("/feed", response_model=list[ActivityResponse])
async def get_activity_feed(
    current_user: OptionalUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[ActivityResponse]:
    service = ActivityService(db)
    activities = await service.get_recent(skip=skip, limit=limit)
    return [ActivityResponse.model_validate(a) for a in activities]


@router.get("/inbox", response_model=InboxResponse)
async def get_inbox(
    current_user: OptionalUser,
    person_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
) -> InboxResponse:
    service = InboxService(db)
    return await service.get_inbox(person_id)
