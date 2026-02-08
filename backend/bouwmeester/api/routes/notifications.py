"""API routes for notifications."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import get_db
from bouwmeester.models.person import Person
from bouwmeester.schema.notification import (
    NotificationCreate,
    NotificationResponse,
    SendMessageRequest,
    UnreadCountResponse,
)
from bouwmeester.services.mention_service import MentionService
from bouwmeester.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    person_id: UUID = Query(...),
    unread_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[NotificationResponse]:
    service = NotificationService(db)
    notifications = await service.get_notifications(
        person_id, unread_only=unread_only, skip=skip, limit=limit
    )
    return [NotificationResponse.model_validate(n) for n in notifications]


@router.get("/count", response_model=UnreadCountResponse)
async def get_unread_count(
    person_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
) -> UnreadCountResponse:
    service = NotificationService(db)
    count = await service.count_unread(person_id)
    return UnreadCountResponse(count=count)


@router.put("/{id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> NotificationResponse:
    service = NotificationService(db)
    notification = await service.mark_read(id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return NotificationResponse.model_validate(notification)


@router.put("/read-all")
async def mark_all_notifications_read(
    person_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    service = NotificationService(db)
    count = await service.mark_all_read(person_id)
    return {"marked_read": count}


@router.post("/send", response_model=NotificationResponse)
async def send_message(
    body: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
) -> NotificationResponse:
    recipient = await db.get(Person, body.person_id)
    if recipient is None:
        raise HTTPException(status_code=404, detail="Recipient not found")
    sender = await db.get(Person, body.sender_id)
    if sender is None:
        raise HTTPException(status_code=404, detail="Sender not found")

    is_agent = recipient.is_agent
    notif_type = "agent_prompt" if is_agent else "direct_message"
    title = f"{'Prompt' if is_agent else 'Bericht'} van {sender.naam}"

    service = NotificationService(db)
    data = NotificationCreate(
        person_id=body.person_id,
        type=notif_type,
        title=title,
        message=body.message,
        sender_id=body.sender_id,
    )
    notification = await service.repo.create(data)

    # Sync mentions from message body
    if body.message:
        mention_svc = MentionService(db)
        new_mentions = await mention_svc.sync_mentions(
            "notification", notification.id, body.message, body.sender_id
        )
        for m in new_mentions:
            if m.mention_type == "person" and m.target_id != body.person_id:
                await service.notify_mention(
                    m.target_id,
                    "notification",
                    title,
                    sender_id=body.sender_id,
                )

    await db.commit()
    return NotificationResponse.model_validate(notification)
