"""Admin API routes — whitelist, users, database backup, access requests."""

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
from bouwmeester.core.encryption import decrypt_value, encrypt_value
from bouwmeester.core.whitelist import refresh_whitelist_cache, seed_admins_from_file
from bouwmeester.models.access_request import AccessRequest
from bouwmeester.models.app_config import AppConfig
from bouwmeester.models.person import Person
from bouwmeester.models.whitelist_email import WhitelistEmail
from bouwmeester.schema.access_request import (
    AccessRequestResponse,
    AccessRequestReviewRequest,
)
from bouwmeester.schema.app_config import AppConfigResponse, AppConfigUpdate
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
from bouwmeester.services.activity_service import ActivityService

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
    """List all whitelisted email addresses (admin only)."""
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
    """Add an email to the access whitelist. Returns 409 if already present."""
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
        added_by=admin.default_email if admin else None,
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
    """Remove an email from the whitelist. Cannot remove your own email."""
    entry = await db.get(WhitelistEmail, id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Whitelist entry niet gevonden",
        )

    # Guard: prevent admin from removing their own email (lockout)
    admin_email = admin.default_email if admin else None
    if admin_email and entry.email == admin_email.strip().lower():
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
    """List all human users (excluding agents) with admin status."""
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
    """Grant or revoke admin status. Cannot revoke your own admin rights."""
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
# Access request endpoints
# ---------------------------------------------------------------------------


@router.get("/access-requests", response_model=list[AccessRequestResponse])
async def list_access_requests(
    admin: AdminUser,
    request_status: str | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[AccessRequestResponse]:
    """List access requests, optionally filtered by status."""
    stmt = select(AccessRequest).order_by(AccessRequest.requested_at.desc())
    if request_status:
        stmt = stmt.where(AccessRequest.status == request_status)
    result = await db.execute(stmt)
    return [AccessRequestResponse.model_validate(row) for row in result.scalars().all()]


@router.patch("/access-requests/{id}", response_model=AccessRequestResponse)
async def review_access_request(
    id: UUID,
    data: AccessRequestReviewRequest,
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> AccessRequestResponse:
    """Approve or deny an access request."""
    access_request = await db.get(AccessRequest, id)
    if access_request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Toegangsverzoek niet gevonden",
        )

    if access_request.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dit verzoek is al beoordeeld",
        )

    access_request.reviewed_at = datetime.now(UTC)
    access_request.reviewed_by_id = admin.id if admin else None

    if data.action == "approve":
        access_request.status = "approved"

        # Add to whitelist
        email = access_request.email.strip().lower()
        existing = await db.execute(
            select(WhitelistEmail).where(WhitelistEmail.email == email)
        )
        if existing.scalar_one_or_none() is None:
            reviewer = admin.default_email if admin else None
            added_label = (
                f"access-request (by {reviewer})" if reviewer else "access-request"
            )
            entry = WhitelistEmail(
                email=email,
                added_by=added_label,
            )
            db.add(entry)

        await db.flush()
        await refresh_whitelist_cache(db)
    else:
        access_request.status = "denied"
        access_request.deny_reason = data.deny_reason
        await db.flush()

    await db.refresh(access_request)
    return AccessRequestResponse.model_validate(access_request)


# ---------------------------------------------------------------------------
# App configuration (LLM keys, model settings, etc.)
# ---------------------------------------------------------------------------

# Default config entries seeded on first admin visit.
_DEFAULT_CONFIG = [
    {
        "key": "ANTHROPIC_API_KEY",
        "value": "",
        "description": "Anthropic API-sleutel voor Claude",
        "is_secret": True,
    },
    {
        "key": "LLM_MODEL",
        "value": "claude-haiku-4-5-20251001",
        "description": "Claude model-ID",
        "is_secret": False,
    },
    {
        "key": "VLAM_API_KEY",
        "value": "",
        "description": "VLAM API-token (soevereine LLM)",
        "is_secret": True,
    },
    {
        "key": "VLAM_BASE_URL",
        "value": "",
        "description": "VLAM API base-URL (OpenAI-compatible endpoint)",
        "is_secret": False,
    },
    {
        "key": "VLAM_MODEL_ID",
        "value": "",
        "description": "VLAM model-ID",
        "is_secret": False,
    },
    {
        "key": "LLM_PROVIDER",
        "value": "claude",
        "description": "Standaard LLM-provider: 'claude' of 'vlam'",
        "is_secret": False,
    },
]


def _mask_secret(value: str) -> str:
    """Mask a secret value for display, showing only last 4 chars."""
    if not value or len(value) <= 4:
        return "****" if value else ""
    return "****" + value[-4:]


# Per-worker optimization flag. ON CONFLICT DO NOTHING ensures correctness
# even when multiple workers race to seed defaults simultaneously.
_defaults_seeded = False


async def _ensure_default_config(db: AsyncSession) -> None:
    """Create default config entries if they don't exist (runs once per worker)."""
    global _defaults_seeded  # noqa: PLW0603
    if _defaults_seeded:
        return

    from sqlalchemy.dialects.postgresql import insert

    for entry in _DEFAULT_CONFIG:
        stmt = (
            insert(AppConfig)
            .values(**entry)
            .on_conflict_do_nothing(index_elements=["key"])
        )
        await db.execute(stmt)
    await db.flush()
    _defaults_seeded = True


@router.get("/config", response_model=list[AppConfigResponse])
async def list_config(
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> list[AppConfigResponse]:
    """List all configuration entries. Secret values are masked."""
    await _ensure_default_config(db)
    result = await db.execute(select(AppConfig).order_by(AppConfig.key))
    entries = []
    for row in result.scalars().all():
        resp = AppConfigResponse.model_validate(row)
        if row.is_secret:
            # Decrypt for masking (show last 4 chars of real value)
            plain = decrypt_value(row.value)
            resp.value = _mask_secret(plain)
        entries.append(resp)
    return entries


@router.patch(
    "/config/{key}",
    response_model=AppConfigResponse,
)
async def update_config(
    key: str,
    data: AppConfigUpdate,
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> AppConfigResponse:
    """Update a configuration value."""
    result = await db.execute(select(AppConfig).where(AppConfig.key == key))
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuratie '{key}' niet gevonden",
        )

    entry.value = encrypt_value(data.value) if entry.is_secret else data.value
    user_label = (admin.default_email or admin.naam) if admin else "anonymous"
    entry.updated_by = user_label
    await db.flush()
    await db.refresh(entry)

    # Clear the LLM factory cache so new values take effect immediately
    from bouwmeester.services.llm import clear_config_cache

    clear_config_cache()

    await ActivityService(db).log_event(
        "admin.config_update",
        actor_id=admin.id if admin else None,
        actor_naam=user_label,
        details={"key": key},
    )

    resp = AppConfigResponse.model_validate(entry)
    if entry.is_secret:
        resp.value = _mask_secret(decrypt_value(entry.value))
    return resp


# ---------------------------------------------------------------------------
# Database backup / restore
# ---------------------------------------------------------------------------


@router.get("/database/export")
async def export_database(
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export full database as pg_dump (optionally age-encrypted)."""
    from bouwmeester.services.database_backup_service import (
        export_database as do_export,
    )

    user_label = (admin.default_email or admin.naam) if admin else "anonymous"
    logger.info("Database export requested by %s", user_label)

    try:
        file_bytes, filename = await asyncio.to_thread(do_export)
    except Exception:
        logger.exception("Database export failed (requested by %s)", user_label)
        raise HTTPException(
            status_code=500, detail="Database export mislukt. Zie server logs."
        )

    await ActivityService(db).log_event(
        "seed.database_export",
        actor_id=admin.id if admin else None,
        actor_naam=user_label,
        details={"description": "Database export uitgevoerd", "filename": filename},
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

    user_label = (admin.default_email or admin.naam) if admin else "anonymous"
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

    # Log audit entry so the first activity record shows who imported the backup
    await ActivityService(db).log_event(
        "seed.database_import",
        actor_id=admin.id if admin else None,
        actor_naam=user_label,
        details={
            "description": "Database import uitgevoerd",
            "filename": file.filename,
            "tables_restored": result.tables_restored,
        },
    )

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
_PRESERVED_TABLES = {
    "whitelist_email",
    "alembic_version",
    "http_sessions",
    "app_config",
}

# All model tables (order doesn't matter — TRUNCATE ... CASCADE handles FKs)
_ALL_MODEL_TABLES = [
    "access_request",
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
    "bron_bijlage",
    "bron",
    "dossier",
    "doel",
    "instrument",
    "beleidskader",
    "maatregel",
    "politieke_input",
    "corpus_node_title",
    "corpus_node_status",
    "corpus_node",
    "person_email",
    "person_phone",
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

    user_label = (admin.default_email or admin.naam) if admin else "anonymous"
    logger.warning("DATABASE RESET requested by %s", user_label)

    tables_to_clear = [t for t in _ALL_MODEL_TABLES if t not in _PRESERVED_TABLES]
    quoted = ", ".join(f'"{t}"' for t in tables_to_clear)
    await db.execute(text(f"TRUNCATE {quoted} CASCADE"))

    admin_created = await seed_admins_from_file(db)
    await refresh_whitelist_cache(db)

    # Log audit entry so the first activity record shows who reset the database
    await ActivityService(db).log_event(
        "seed.database_reset",
        actor_id=admin.id if admin else None,
        actor_naam=user_label,
        details={"description": "Database reset uitgevoerd"},
    )

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
