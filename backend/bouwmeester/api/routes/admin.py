"""Admin API routes — whitelist management and user admin."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import AdminUser
from bouwmeester.core.database import get_db
from bouwmeester.core.whitelist import refresh_whitelist_cache
from bouwmeester.models.person import Person
from bouwmeester.models.whitelist_email import WhitelistEmail
from bouwmeester.schema.whitelist import (
    AdminToggleRequest,
    AdminUserResponse,
    WhitelistEmailCreate,
    WhitelistEmailResponse,
)

router = APIRouter(prefix="/admin", tags=["admin"])

# ---------------------------------------------------------------------------
# Whitelist endpoints
# ---------------------------------------------------------------------------


@router.get("/whitelist", response_model=list[WhitelistEmailResponse])
async def list_whitelist(
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> list[WhitelistEmailResponse]:
    result = await db.execute(
        select(WhitelistEmail).order_by(WhitelistEmail.created_at.desc())
    )
    return [
        WhitelistEmailResponse.model_validate(row) for row in result.scalars().all()
    ]


@router.post(
    "/whitelist",
    response_model=WhitelistEmailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_whitelist_email(
    data: WhitelistEmailCreate,
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> WhitelistEmailResponse:
    email = data.email.strip().lower()

    existing = await db.execute(
        select(WhitelistEmail).where(WhitelistEmail.email == email)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"E-mailadres '{email}' staat al op de toegangslijst",
        )

    entry = WhitelistEmail(
        email=email,
        added_by=admin.email if admin else None,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)

    await refresh_whitelist_cache(db)

    return WhitelistEmailResponse.model_validate(entry)


@router.delete("/whitelist/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_whitelist_email(
    id: UUID,
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    entry = await db.get(WhitelistEmail, id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Whitelist entry niet gevonden",
        )

    await db.delete(entry)
    await db.flush()

    await refresh_whitelist_cache(db)


# ---------------------------------------------------------------------------
# User management endpoints
# ---------------------------------------------------------------------------


@router.get("/users", response_model=list[AdminUserResponse])
async def list_admin_users(
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> list[AdminUserResponse]:
    result = await db.execute(
        select(Person)
        .where(Person.is_agent == False)  # noqa: E712
        .order_by(Person.naam)
    )
    return [AdminUserResponse.model_validate(p) for p in result.scalars().all()]


@router.patch("/users/{id}", response_model=AdminUserResponse)
async def toggle_admin(
    id: UUID,
    data: AdminToggleRequest,
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    person = await db.get(Person, id)
    if person is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Persoon niet gevonden",
        )

    # Guard: admin cannot remove their own admin status
    if admin and admin.id == id and not data.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Je kunt je eigen admin-rechten niet intrekken",
        )

    person.is_admin = data.is_admin
    await db.flush()
    await db.refresh(person)

    return AdminUserResponse.model_validate(person)
