"""Shared query utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from bouwmeester.models.person import Person


def escape_like(value: str) -> str:
    """Escape special characters for use in SQL LIKE / ILIKE patterns."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def normalize_email(email: str) -> str:
    """Normalize an email address for consistent comparison."""
    return email.strip().lower()


async def find_person_by_email(session: AsyncSession, email: str) -> Person | None:
    """Find a Person by normalized email via the ``PersonEmail`` table.

    ``PersonEmail.email`` is unique, so this identifies at most one person.
    The legacy ``Person.email`` column is deliberately not consulted: it is
    not unique and is free text, so it must never decide identity.
    """
    from sqlalchemy import func, select

    from bouwmeester.models.person import Person as PersonModel
    from bouwmeester.models.person_email import PersonEmail

    stmt = (
        select(PersonModel)
        .join(PersonEmail)
        .where(func.lower(PersonEmail.email) == normalize_email(email))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
