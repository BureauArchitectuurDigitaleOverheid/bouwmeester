"""API routes for notifications."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_found
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.models.notification import Notification
from bouwmeester.models.person import Person
from bouwmeester.schema.notification import (
    DashboardStatsResponse,
    NotificationCreate,
    NotificationResponse,
    ReactionRequest,
    ReactionSummary,
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
    """Build NotificationResponse with sender_name and reply_count (single item)."""
    resp = NotificationResponse.model_validate(notification)
    if notification.sender_id:
        sender = await db.get(Person, notification.sender_id)
        if sender:
            resp.sender_name = sender.naam
    if notification.parent_id is None:
        # For DM roots, replies are parented to thread_id (the recipient's root)
        count_id = notification.thread_id if notification.thread_id else notification.id
        resp.reply_count = await service.repo.count_replies(count_id)
        activity = await service.repo.last_activity_batch([count_id])
        if count_id in activity:
            resp.last_activity_at = activity[count_id][0]
            resp.last_message = activity[count_id][1]
    return resp


async def _enrich_batch(
    notifications: list[Notification],
    service: NotificationService,
    db: AsyncSession,
) -> list[NotificationResponse]:
    """Batch-enrich notifications: load sender names and reply counts in bulk."""
    if not notifications:
        return []

    # Batch-load sender names
    sender_ids = {n.sender_id for n in notifications if n.sender_id}
    sender_map: dict[UUID, str] = {}
    if sender_ids:
        stmt = select(Person.id, Person.naam).where(Person.id.in_(sender_ids))
        result = await db.execute(stmt)
        sender_map = {row.id: row.naam for row in result.all()}

    # Batch-load reply counts and last activity for root notifications
    # For DM roots, replies are parented to thread_id (the recipient's root)
    count_ids = []
    for n in notifications:
        if n.parent_id is None:
            count_ids.append(n.thread_id if n.thread_id else n.id)
    reply_counts = await service.repo.count_replies_batch(count_ids)
    last_activity = await service.repo.last_activity_batch(count_ids)

    responses = []
    for n in notifications:
        resp = NotificationResponse.model_validate(n)
        if n.sender_id and n.sender_id in sender_map:
            resp.sender_name = sender_map[n.sender_id]
        if n.parent_id is None:
            count_id = n.thread_id if n.thread_id else n.id
            resp.reply_count = reply_counts.get(count_id, 0)
            if count_id in last_activity:
                resp.last_activity_at = last_activity[count_id][0]
                resp.last_message = last_activity[count_id][1]
        responses.append(resp)

    return responses


async def _attach_reactions(
    responses: list[NotificationResponse],
    service: NotificationService,
    db: AsyncSession,
    current_person_id: UUID | None = None,
) -> None:
    """Fetch reactions for a list of NotificationResponses and attach them in-place."""
    message_ids = [r.id for r in responses]
    if not message_ids:
        return
    reactions_map = await service.repo.get_reactions_for_messages(message_ids)

    # Pre-fetch sender names for reaction senders
    all_sender_ids = {
        r.sender_id for rlist in reactions_map.values() for r in rlist if r.sender_id
    }
    sender_name_map: dict[UUID, str] = {}
    if all_sender_ids:
        stmt = select(Person.id, Person.naam).where(Person.id.in_(all_sender_ids))
        result = await db.execute(stmt)
        sender_name_map = {row.id: row.naam for row in result.all()}

    resp_by_id = {r.id: r for r in responses}
    for msg_id, reaction_list in reactions_map.items():
        if msg_id not in resp_by_id:
            continue
        # Group by emoji
        emoji_groups: dict[str, list[Notification]] = {}
        for r in reaction_list:
            emoji_groups.setdefault(r.message or "", []).append(r)
        summaries = []
        for emoji, group in emoji_groups.items():
            summaries.append(
                ReactionSummary(
                    emoji=emoji,
                    count=len(group),
                    sender_names=[
                        sender_name_map.get(r.sender_id, "")
                        for r in group
                        if r.sender_id
                    ],
                    reacted_by_me=any(r.sender_id == current_person_id for r in group)
                    if current_person_id
                    else False,
                )
            )
        resp_by_id[msg_id].reactions = summaries


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    current_user: OptionalUser,
    person_id: UUID = Query(...),
    unread_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[NotificationResponse]:
    """List notifications for a person, sorted by latest activity.

    Filter with unread_only.
    """
    service = NotificationService(db)
    notifications = await service.get_notifications(
        person_id, unread_only=unread_only, skip=skip, limit=limit
    )
    responses = await _enrich_batch(notifications, service, db)
    # Re-sort so threads with recent replies bubble to the top
    responses.sort(key=lambda r: r.last_activity_at or r.created_at, reverse=True)
    return responses


@router.get("/count", response_model=UnreadCountResponse)
async def get_unread_count(
    current_user: OptionalUser,
    person_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
) -> UnreadCountResponse:
    """Get the count of unread notifications for a person."""
    service = NotificationService(db)
    count = await service.count_unread(person_id)
    return UnreadCountResponse(count=count)


@router.get("/dashboard-stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    current_user: OptionalUser,
    person_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
) -> DashboardStatsResponse:
    """Return dashboard statistics for a person."""
    service = NotificationService(db)
    stats = await service.get_dashboard_stats(person_id)
    return DashboardStatsResponse(**stats)


@router.get("/{id}", response_model=NotificationResponse)
async def get_notification(
    id: UUID,
    current_user: OptionalUser,
    person_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> NotificationResponse:
    """Get a single notification by ID with sender name, reply count, and reactions."""
    service = NotificationService(db)
    notification = require_found(await service.repo.get_by_id(id), "Notification")
    resp = await _enrich_response(notification, service, db)
    await _attach_reactions([resp], service, db, person_id)
    return resp


@router.get("/{id}/replies", response_model=list[NotificationResponse])
async def get_replies(
    id: UUID,
    current_user: OptionalUser,
    person_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[NotificationResponse]:
    """Get all replies in a notification thread, with reactions attached."""
    service = NotificationService(db)
    notification = require_found(await service.repo.get_by_id(id), "Notification")
    # Use thread_id to fetch replies (replies are parented to the recipient's root)
    reply_parent_id = notification.thread_id if notification.thread_id else id
    replies = await service.repo.get_replies(reply_parent_id)
    responses = await _enrich_batch(replies, service, db)
    await _attach_reactions(responses, service, db, person_id)
    return responses


@router.put("/{id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> NotificationResponse:
    """Mark a single notification as read."""
    service = NotificationService(db)
    notification = require_found(await service.mark_read(id), "Notification")
    return await _enrich_response(notification, service, db)


@router.put("/read-all")
async def mark_all_notifications_read(
    current_user: OptionalUser,
    person_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Mark all notifications as read for a person. Returns count marked."""
    service = NotificationService(db)
    count = await service.mark_all_read(person_id)
    return {"marked_read": count}


@router.post("/send", response_model=NotificationResponse)
async def send_message(
    body: SendMessageRequest,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> NotificationResponse:
    """Send a direct message to a person. Creates thread roots for both parties."""
    # Prevent sender spoofing when authenticated
    if current_user is not None and body.sender_id != current_user.id:
        raise HTTPException(403, "Sender moet de ingelogde gebruiker zijn")

    recipient = require_found(await db.get(Person, body.person_id), "Recipient")
    sender = require_found(await db.get(Person, body.sender_id), "Sender")

    is_agent = recipient.is_agent
    notif_type = "agent_prompt" if is_agent else "direct_message"
    title = f"{'Prompt' if is_agent else 'Bericht'} van {sender.naam}"

    service = NotificationService(db)

    # Create recipient's root (unread)
    recipient_data = NotificationCreate(
        person_id=body.person_id,
        type=notif_type,
        title=title,
        message=body.message,
        sender_id=body.sender_id,
    )
    recipient_root = await service.repo.create(recipient_data)
    await db.flush()

    # Set thread_id on recipient's root (points to itself)
    recipient_root.thread_id = recipient_root.id
    await db.flush()

    # Create sender's root (read — they sent it)
    sender_data = NotificationCreate(
        person_id=body.sender_id,
        type=notif_type,
        title=f"{'Prompt' if is_agent else 'Bericht'} aan {recipient.naam}",
        message=body.message,
        sender_id=body.sender_id,
        thread_id=recipient_root.id,
    )
    sender_root = await service.repo.create(sender_data)
    sender_root.is_read = True
    await db.flush()

    await sync_and_notify_mentions(
        db,
        "notification",
        recipient_root.id,
        body.message,
        title,
        sender_id=body.sender_id,
        exclude_person_id=body.person_id,
    )

    return await _enrich_response(sender_root, service, db)


@router.post("/{id}/reply", response_model=NotificationResponse)
async def reply_to_notification(
    id: UUID,
    body: ReplyRequest,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> NotificationResponse:
    """Reply to a notification thread. Marks the other party's root as unread."""
    # Prevent sender spoofing when authenticated
    if current_user is not None and body.sender_id != current_user.id:
        raise HTTPException(403, "Sender moet de ingelogde gebruiker zijn")

    service = NotificationService(db)
    parent = require_found(await service.repo.get_by_id(id), "Notification")

    # If replying to a reply, thread up to the root parent
    root = parent
    if parent.parent_id:
        root = require_found(
            await service.repo.get_by_id(parent.parent_id), "Notification"
        )

    # Determine the thread_id — the recipient's root ID that all replies parent to
    thread_id = root.thread_id if root.thread_id else root.id

    sender = require_found(await db.get(Person, body.sender_id), "Sender")
    title = f"Reactie van {sender.naam}"

    # Find the other party's root so we can mark it unread.
    # get_other_root queries for thread_id=thread_id AND person_id != sender_id,
    # which works regardless of whether the sender replies from their own root
    # or from the recipient's root — in both cases sender_id identifies the
    # replier and the "other" root belongs to the counterparty.
    other_root = await service.repo.get_other_root(thread_id, body.sender_id)
    reply_recipient = other_root.person_id if other_root else root.person_id

    data = NotificationCreate(
        person_id=reply_recipient,
        type="direct_message",
        title=title,
        message=body.message,
        sender_id=body.sender_id,
        parent_id=thread_id,
        related_node_id=root.related_node_id,
        related_task_id=root.related_task_id,
    )
    reply = await service.repo.create(data)

    # Mark the other party's root as unread
    if other_root:
        other_root.is_read = False
        await db.flush()

    await sync_and_notify_mentions(
        db,
        "notification",
        reply.id,
        body.message,
        title,
        sender_id=body.sender_id,
        exclude_person_id=reply_recipient,
    )

    return await _enrich_response(reply, service, db)


@router.post("/{id}/react")
async def react_to_message(
    id: UUID,
    body: ReactionRequest,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Toggle an emoji reaction on a message. Returns action taken."""
    if current_user is not None and body.sender_id != current_user.id:
        raise HTTPException(403, "Sender moet de ingelogde gebruiker zijn")

    service = NotificationService(db)
    message = require_found(await service.repo.get_by_id(id), "Notification")

    # Check for existing reaction — toggle off if found
    existing = await service.repo.find_existing_reaction(
        message.id, body.sender_id, body.emoji
    )
    if existing:
        await service.repo.delete(existing)
        return {"action": "removed"}

    # Create new reaction: parent_id = the specific message being reacted to
    sender = require_found(await db.get(Person, body.sender_id), "Sender")
    data = NotificationCreate(
        person_id=message.person_id,
        type="emoji_reaction",
        title=f"{sender.naam} reageerde met {body.emoji}",
        message=body.emoji,
        sender_id=body.sender_id,
        parent_id=message.id,
    )
    await service.repo.create(data)
    return {"action": "added"}
