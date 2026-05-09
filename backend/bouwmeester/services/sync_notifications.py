"""Helpers om sync-events naar super_admins te broadcasten als notification.

Wordt gebruikt door TOOI-sync (sanity-skip), reconciliation-aanmaak en
andere sync-services die super_admin-aandacht nodig hebben.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.role import PersonRole
from bouwmeester.schema.notification import NotificationCreate, NotificationType
from bouwmeester.services.notification_service import NotificationService

log = logging.getLogger(__name__)


async def _super_admin_person_ids(session: AsyncSession) -> list:
    """Pak alle super_admin person_ids op basis van role_id='super_admin'."""
    rows = (
        (
            await session.execute(
                select(PersonRole.person_id).where(
                    PersonRole.role_id == "super_admin",
                    PersonRole.eind_datum.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    return list({pid for pid in rows if pid})


async def notify_super_admins(
    session: AsyncSession,
    *,
    title: str,
    message: str,
) -> int:
    """Stuur een sync_alert-notificatie naar alle super_admins.

    Returns het aantal notifications dat aangemaakt is.
    """
    person_ids = await _super_admin_person_ids(session)
    if not person_ids:
        log.warning("Geen super_admins gevonden voor sync-alert: %s", title)
        return 0

    svc = NotificationService(session)
    n = 0
    for pid in person_ids:
        await svc.send(
            NotificationCreate(
                person_id=pid,
                type=NotificationType.sync_alert,
                title=title,
                message=message,
            )
        )
        n += 1
    return n
