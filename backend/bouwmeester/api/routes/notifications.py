"""API routes for notifications."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_found
from bouwmeester.core.database import get_db
from bouwmeester.models.notification import Notification
from bouwmeester.models.person import Person
from bouwmeester.schema.notification import (
    NotificationCreate,
    NotificationResponse,
    ReplyRequest,
    SendMessageRequest,
    UnreadCountResponse,
)
from bouwmeester.services.mention_helper import sync_and_notify_mentions
from bouwmeester.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


async def _enrich_response(
    notification: Notification,
    service: NotificationService,
    db: AsyncSession,
) -> NotificationResponse:
    """Build NotificationResponse with sender_name and reply_count."""
    resp = NotificationResponse.model_validate(notification)
    if notification.sender_id:
        sender = await db.get(Person, notification.sender_id)
        if sender:
            resp.sender_name = sender.naam
    if notification.parent_id is None:
        resp.reply_count = await service.repo.count_replies(notification.id)
    return resp


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
    return [await _enrich_response(n, service, db) for n in notifications]


@router.get("/count", response_model=UnreadCountResponse)
async def get_unread_count(
    person_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
) -> UnreadCountResponse:
    service = NotificationService(db)
    count = await service.count_unread(person_id)
    return UnreadCountResponse(count=count)


@router.get("/{id}", response_model=NotificationResponse)
async def get_notification(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> NotificationResponse:
    service = NotificationService(db)
    notification = require_found(await service.repo.get_by_id(id), "Notification")
    return await _enrich_response(notification, service, db)


@router.get("/{id}/replies", response_model=list[NotificationResponse])
async def get_replies(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[NotificationResponse]:
    service = NotificationService(db)
    # Verify parent exists
    require_found(await service.repo.get_by_id(id), "Notification")
    replies = await service.repo.get_replies(id)
    return [await _enrich_response(r, service, db) for r in replies]


@router.put("/{id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> NotificationResponse:
    service = NotificationService(db)
    notification = require_found(await service.mark_read(id), "Notification")
    return await _enrich_response(notification, service, db)


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
    recipient = require_found(await db.get(Person, body.person_id), "Recipient")
    sender = require_found(await db.get(Person, body.sender_id), "Sender")

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

    await sync_and_notify_mentions(
        db,
        "notification",
        notification.id,
        body.message,
        title,
        sender_id=body.sender_id,
        exclude_person_id=body.person_id,
    )

    await db.commit()
    return await _enrich_response(notification, service, db)


@router.post("/{id}/reply", response_model=NotificationResponse)
async def reply_to_notification(
    id: UUID,
    body: ReplyRequest,
    db: AsyncSession = Depends(get_db),
) -> NotificationResponse:
    service = NotificationService(db)
    parent = require_found(await service.repo.get_by_id(id), "Notification")

    # If replying to a reply, thread up to the root parent
    root_id = parent.parent_id if parent.parent_id else parent.id
    root = (
        parent
        if not parent.parent_id
        else require_found(await service.repo.get_by_id(root_id), "Notification")
    )

    sender = require_found(await db.get(Person, body.sender_id), "Sender")
    title = f"Reactie van {sender.naam}"

    data = NotificationCreate(
        person_id=root.person_id,
        type="direct_message",
        title=title,
        message=body.message,
        sender_id=body.sender_id,
        parent_id=root_id,
        related_node_id=root.related_node_id,
        related_task_id=root.related_task_id,
    )
    reply = await service.repo.create(data)

    # Also notify the original sender if they are different from the replier
    # and different from the root recipient
    should_notify_sender = (
        root.sender_id
        and root.sender_id != body.sender_id
        and root.sender_id != root.person_id
    )
    if should_notify_sender:
        notify_data = NotificationCreate(
            person_id=root.sender_id,
            type="direct_message",
            title=title,
            message=body.message,
            sender_id=body.sender_id,
            parent_id=root_id,
            related_node_id=root.related_node_id,
            related_task_id=root.related_task_id,
        )
        await service.repo.create(notify_data)

    await sync_and_notify_mentions(
        db,
        "notification",
        reply.id,
        body.message,
        title,
        sender_id=body.sender_id,
        exclude_person_id=root.person_id,
    )

    await db.commit()
    return await _enrich_response(reply, service, db)
