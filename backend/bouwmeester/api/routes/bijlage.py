"""API routes for file attachments on Bron nodes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.storage import (
    BRON_ALLOWED_CONTENT_TYPES,
    ensure_bijlagen_dir,
    read_upload_content,
    safe_resolve_or_400,
    sanitize_download_filename,
    validate_upload,
    write_upload_to_disk,
)
from bouwmeester.models.bron import Bron
from bouwmeester.models.bron_bijlage import BronBijlage
from bouwmeester.schema.bron import BronBijlageResponse
from bouwmeester.services.activity_service import log_activity

router = APIRouter(prefix="/nodes/{node_id}/bijlage", tags=["bijlage"])

BIJLAGEN_ROOT = ensure_bijlagen_dir()


async def _get_bron(
    node_id: uuid.UUID, db: AsyncSession, *, load_bijlage: bool = False
) -> Bron:
    stmt = select(Bron).where(Bron.id == node_id)
    if load_bijlage:
        stmt = stmt.options(selectinload(Bron.bijlage))
    result = await db.execute(stmt)
    bron = result.scalar_one_or_none()
    if bron is None:
        raise HTTPException(
            status_code=404,
            detail="Bron not found (node is not a bron type)",
        )
    return bron


@router.post(
    "", response_model=BronBijlageResponse, status_code=status.HTTP_201_CREATED
)
async def upload_bijlage(
    node_id: uuid.UUID,
    file: UploadFile,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> BronBijlageResponse:
    """Upload a file attachment to a bron node. Replaces existing attachment."""
    bron = await _get_bron(node_id, db, load_bijlage=True)

    content_type = file.content_type or ""
    content = await read_upload_content(file)
    validate_upload(content, content_type, allowed=BRON_ALLOWED_CONTENT_TYPES)

    # Write new file first (before deleting old one, to avoid data loss
    # on write failure).
    filename, relative_path, _ = write_upload_to_disk(
        content, file.filename or "bijlage", BIJLAGEN_ROOT, item_id=node_id
    )

    # Remove existing bijlage if present (file + DB row).
    if bron.bijlage:
        old_path = safe_resolve_or_400(BIJLAGEN_ROOT, bron.bijlage.pad)
        if old_path.exists():
            old_path.unlink()
        await db.delete(bron.bijlage)
        await db.flush()

    bijlage = BronBijlage(
        bron_id=bron.id,
        bestandsnaam=filename,
        content_type=content_type,
        bestandsgrootte=len(content),
        pad=relative_path,
    )
    db.add(bijlage)
    await db.flush()
    await db.refresh(bijlage)

    await log_activity(
        db,
        current_user,
        None,
        "bijlage.uploaded",
        node_id=node_id,
        details={"filename": filename},
    )

    return BronBijlageResponse.model_validate(bijlage)


@router.get("", response_model=BronBijlageResponse | None)
async def get_bijlage_info(
    node_id: uuid.UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> BronBijlageResponse | None:
    """Get metadata about a bron node's attachment (filename, size, type)."""
    bron = await _get_bron(node_id, db)

    result = await db.execute(select(BronBijlage).where(BronBijlage.bron_id == bron.id))
    bijlage = result.scalar_one_or_none()
    if bijlage is None:
        return None
    return BronBijlageResponse.model_validate(bijlage)


@router.get("/download")
async def download_bijlage(
    node_id: uuid.UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Download the file attachment of a bron node."""
    bron = await _get_bron(node_id, db)

    result = await db.execute(select(BronBijlage).where(BronBijlage.bron_id == bron.id))
    bijlage = result.scalar_one_or_none()
    if bijlage is None:
        raise HTTPException(status_code=404, detail="Geen bijlage gevonden")

    file_path = safe_resolve_or_400(BIJLAGEN_ROOT, bijlage.pad)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Bestand niet gevonden op disk")

    return FileResponse(
        path=str(file_path),
        filename=sanitize_download_filename(bijlage.bestandsnaam),
        media_type="application/octet-stream",
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bijlage(
    node_id: uuid.UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a bron node's file attachment (DB record and file on disk)."""
    bron = await _get_bron(node_id, db)

    result = await db.execute(select(BronBijlage).where(BronBijlage.bron_id == bron.id))
    bijlage = result.scalar_one_or_none()
    if bijlage is None:
        raise HTTPException(status_code=404, detail="Geen bijlage gevonden")

    file_path = safe_resolve_or_400(BIJLAGEN_ROOT, bijlage.pad)
    bijlage_naam = bijlage.bestandsnaam
    await db.delete(bijlage)

    await log_activity(
        db,
        current_user,
        None,
        "bijlage.deleted",
        node_id=node_id,
        details={"filename": bijlage_naam},
    )

    # Delete file after DB delete succeeds (commit happens in get_db).
    if file_path.exists():
        file_path.unlink()
