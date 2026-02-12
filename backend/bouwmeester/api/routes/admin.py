"""Admin API routes — whitelist management, user admin, database backup."""

import asyncio
import io
import logging
import os
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import AdminUser
from bouwmeester.core.database import get_db
from bouwmeester.core.whitelist import refresh_whitelist_cache, seed_admins_from_file
from bouwmeester.models.person import Person
from bouwmeester.models.whitelist_email import WhitelistEmail
from bouwmeester.schema.database_backup import (
    DatabaseBackupInfo,
    DatabaseResetRequest,
    DatabaseResetResult,
    DatabaseRestoreResult,
)
from bouwmeester.schema.whitelist import (
    AdminToggleRequest,
    AdminUserResponse,
    WhitelistEmailCreate,
    WhitelistEmailResponse,
)

logger = logging.getLogger(__name__)

MAX_BACKUP_SIZE = 500 * 1024 * 1024  # 500 MB

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

    # Guard: prevent admin from removing their own email (lockout protection)
    if admin and admin.email and entry.email == admin.email.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Je kunt je eigen e-mailadres niet van de toegangslijst verwijderen",
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
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[AdminUserResponse]:
    result = await db.execute(
        select(Person)
        .where(Person.is_agent == False)  # noqa: E712
        .order_by(Person.naam)
        .offset(skip)
        .limit(limit)
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


# ---------------------------------------------------------------------------
# Database backup / restore
# ---------------------------------------------------------------------------


@router.get("/database/export")
async def export_database(
    admin: AdminUser,
) -> StreamingResponse:
    """Export full database as pg_dump (optionally age-encrypted)."""
    from bouwmeester.services.database_backup_service import (
        export_database as do_export,
    )

    user_label = (admin.email or admin.naam) if admin else "anonymous"
    logger.info("Database export requested by %s", user_label)

    try:
        file_bytes, filename = await asyncio.to_thread(do_export)
    except Exception:
        logger.exception("Database export failed (requested by %s)", user_label)
        raise HTTPException(
            status_code=500, detail="Database export mislukt. Zie server logs."
        )

    logger.info(
        "Database export completed: %s (%s bytes, by %s)",
        filename,
        len(file_bytes),
        user_label,
    )
    media_type = (
        "application/octet-stream" if filename.endswith(".age") else "application/gzip"
    )
    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/database/info", response_model=DatabaseBackupInfo)
async def export_database_info(
    admin: AdminUser,
) -> DatabaseBackupInfo:
    """Return metadata about the current database (revision, etc.)."""
    from bouwmeester.services.database_backup_service import _get_alembic_revision

    revision = await asyncio.to_thread(_get_alembic_revision)
    return DatabaseBackupInfo(
        exported_at=datetime.now(UTC).isoformat(),
        alembic_revision=revision,
        format_version=1,
        encrypted=bool(os.environ.get("AGE_SECRET_KEY", "")),
    )


@router.post("/database/import", response_model=DatabaseRestoreResult)
async def import_database(
    file: UploadFile,
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> DatabaseRestoreResult:
    """Upload a database backup and restore it."""
    from bouwmeester.services.database_backup_service import (
        import_database as do_import,
    )

    user_label = (admin.email or admin.naam) if admin else "anonymous"
    content = await file.read()
    if len(content) > MAX_BACKUP_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Bestand te groot (max {MAX_BACKUP_SIZE // 1024 // 1024} MB)",
        )
    logger.info(
        "Database import requested by %s (file: %s, %s bytes)",
        user_label,
        file.filename,
        len(content),
    )
    try:
        result = await asyncio.to_thread(do_import, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception:
        logger.exception("Database import failed (requested by %s)", user_label)
        raise HTTPException(
            status_code=500, detail="Database import mislukt. Zie server logs."
        )

    # Ensure admin persons exist after import (import may have wiped them)
    admin_created = await seed_admins_from_file(db)
    if admin_created:
        logger.info("Created %d admin person stubs after import", admin_created)

    # Refresh whitelist cache — imported backup may contain different whitelist
    await refresh_whitelist_cache(db)

    logger.info(
        "Database import completed by %s: %s tables, revision %s→%s",
        user_label,
        result.tables_restored,
        result.alembic_revision_from,
        result.alembic_revision_to,
    )
    return result


# ---------------------------------------------------------------------------
# Database reset
# ---------------------------------------------------------------------------

# Tables to preserve during reset
_PRESERVED_TABLES = {"whitelist_email", "alembic_version", "http_sessions"}

# All model tables (order doesn't matter — TRUNCATE ... CASCADE handles FKs)
_ALL_MODEL_TABLES = [
    "notification",
    "mention",
    "suggested_edge",
    "parlementair_item",
    "node_tag",
    "tag",
    "task",
    "node_stakeholder",
    "edge",
    "edge_type",
    "probleem",
    "effect",
    "beleidsoptie",
    "dossier",
    "doel",
    "instrument",
    "beleidskader",
    "maatregel",
    "politieke_input",
    "corpus_node_title",
    "corpus_node_status",
    "corpus_node",
    "person_organisatie_eenheid",
    "organisatie_eenheid_manager",
    "organisatie_eenheid_parent",
    "organisatie_eenheid_naam",
    "activity",
    "absence",
    "team_member",
    "team",
    "person",
    "organisatie_eenheid",
]


@router.post("/database/reset", response_model=DatabaseResetResult)
async def reset_database(
    data: DatabaseResetRequest,
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> DatabaseResetResult:
    """Wipe all data except whitelist, sessions, and alembic version.

    Re-creates admin person stubs so admins keep access after reset.
    """
    if data.confirm != "RESET":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Bevestig de reset door confirm op "RESET" te zetten.',
        )

    user_label = (admin.email or admin.naam) if admin else "anonymous"
    logger.warning("DATABASE RESET requested by %s", user_label)

    tables_to_clear = [t for t in _ALL_MODEL_TABLES if t not in _PRESERVED_TABLES]
    quoted = ", ".join(f'"{t}"' for t in tables_to_clear)
    await db.execute(text(f"TRUNCATE {quoted} CASCADE"))

    admin_created = await seed_admins_from_file(db)
    await refresh_whitelist_cache(db)

    logger.warning(
        "DATABASE RESET completed by %s: %d tables cleared, %d admin stubs created",
        user_label,
        len(tables_to_clear),
        admin_created,
    )

    return DatabaseResetResult(
        success=True,
        tables_cleared=len(tables_to_clear),
        admin_persons_created=admin_created,
        message=f"Database gereset: {len(tables_to_clear)} tabellen gewist, "
        f"{admin_created} admin-accounts aangemaakt.",
    )
