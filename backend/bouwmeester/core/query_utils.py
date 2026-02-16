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
    """Find a Person by normalized email (PersonEmail table → legacy Person.email).

    Performs case-insensitive lookup across both the ``PersonEmail`` join table
    and the legacy ``Person.email`` column.  Returns ``None`` when no match is
    found.
    """
    from sqlalchemy import func, select

    from bouwmeester.models.person import Person as PersonModel
    from bouwmeester.models.person_email import PersonEmail

    email = normalize_email(email)

    # Primary: look up via person_email join table.
    stmt = (
        select(PersonModel)
        .join(PersonEmail)
        .where(func.lower(PersonEmail.email) == email)
    )
    result = await session.execute(stmt)
    person = result.scalar_one_or_none()
    if person is not None:
        return person

    # Fallback: legacy Person.email column.
    stmt = select(PersonModel).where(func.lower(PersonModel.email) == email)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
