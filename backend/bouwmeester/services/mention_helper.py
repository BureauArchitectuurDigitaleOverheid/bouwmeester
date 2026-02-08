"""Helper to sync mentions from content and notify mentioned persons."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.services.mention_service import MentionService
from bouwmeester.services.notification_service import NotificationService


async def sync_and_notify_mentions(
    db: AsyncSession,
    source_type: str,
    source_id: UUID,
    content: str | None,
    entity_title: str,
    *,
    sender_id: UUID | None = None,
    source_node_id: UUID | None = None,
    source_task_id: UUID | None = None,
    exclude_person_id: UUID | None = None,
) -> None:
    """Sync mentions from content and send notifications to mentioned persons.

    Args:
        db: Database session.
        source_type: Type of entity ("node", "task", "organisatie", "notification").
        source_id: ID of the source entity.
        content: Text content to scan for mentions. No-op if None/empty.
        entity_title: Title shown in the notification.
        sender_id: Person who created the mention (optional).
        source_node_id: Related node ID for notification linking (optional).
        source_task_id: Related task ID for notification linking (optional).
        exclude_person_id: Person ID to skip notifying (e.g. the direct recipient).
    """
    if not content:
        return

    mention_svc = MentionService(db)
    new_mentions = await mention_svc.sync_mentions(
        source_type, source_id, content, sender_id
    )

    notif_svc = NotificationService(db)
    for m in new_mentions:
        if m.mention_type == "person":
            if exclude_person_id and m.target_id == exclude_person_id:
                continue
            await notif_svc.notify_mention(
                m.target_id,
                source_type,
                entity_title,
                source_node_id=source_node_id,
                source_task_id=source_task_id,
                sender_id=sender_id,
            )
