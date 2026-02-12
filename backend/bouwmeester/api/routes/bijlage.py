"""API routes for file attachments on Bron nodes."""

import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.models.bron import Bron
from bouwmeester.models.bron_bijlage import BronBijlage
from bouwmeester.schema.bron import BronBijlageResponse

router = APIRouter(prefix="/nodes/{node_id}/bijlage", tags=["bijlage"])


def _default_bijlagen_root() -> str:
    data_path = os.environ.get("DATA_PATH")
    if data_path:
        return os.path.join(data_path, "bijlagen")
    return "/app/bijlagen"


BIJLAGEN_ROOT = Path(os.environ.get("BIJLAGEN_ROOT", _default_bijlagen_root()))
try:
    BIJLAGEN_ROOT.mkdir(parents=True, exist_ok=True)
except OSError:
    pass  # May fail in CI/test; directory is also created per-upload
MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20 MB

logger = logging.getLogger(__name__)
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
    "text/plain",
    "image/png",
    "image/jpeg",
}


def _safe_path(relative: str) -> Path:
    """Resolve a relative path under BIJLAGEN_ROOT, guarding against traversal."""
    resolved = (BIJLAGEN_ROOT / relative).resolve()
    if not str(resolved).startswith(str(BIJLAGEN_ROOT.resolve())):
        raise HTTPException(status_code=400, detail="Ongeldig pad")
    return resolved


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
    bron = await _get_bron(node_id, db, load_bijlage=True)

    content_type = file.content_type or ""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Ongeldig bestandstype: {content_type}. "
                "Toegestaan: PDF, Word, ODT, TXT, PNG, JPEG."
            ),
        )

    # Read file in chunks to avoid loading arbitrarily large uploads into memory.
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(8192):
        total += len(chunk)
        if total > MAX_UPLOAD_SIZE:
            max_mb = MAX_UPLOAD_SIZE // (1024 * 1024)
            raise HTTPException(
                status_code=400,
                detail=f"Bestand te groot. Maximum is {max_mb} MB.",
            )
        chunks.append(chunk)
    content = b"".join(chunks)

    # Sanitize filename: strip path components, keep only the basename.
    raw_name = file.filename or "bijlage"
    filename = Path(raw_name).name or "bijlage"
    safe_name = f"{uuid.uuid4().hex}_{filename}"

    # Write new file first (before deleting old one, to avoid data loss
    # on write failure).
    dir_path = BIJLAGEN_ROOT / str(node_id)
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        new_file_path = dir_path / safe_name
        new_file_path.write_bytes(content)
    except OSError as exc:
        logger.exception("Failed to write bijlage to %s", dir_path)
        raise HTTPException(
            status_code=500,
            detail=f"Kan bestand niet opslaan op disk: {exc}",
        ) from exc

    relative_path = f"{node_id}/{safe_name}"

    # Remove existing bijlage if present (file + DB row).
    if bron.bijlage:
        old_path = _safe_path(bron.bijlage.pad)
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

    return BronBijlageResponse.model_validate(bijlage)


@router.get("", response_model=BronBijlageResponse | None)
async def get_bijlage_info(
    node_id: uuid.UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> BronBijlageResponse | None:
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
    bron = await _get_bron(node_id, db)

    result = await db.execute(select(BronBijlage).where(BronBijlage.bron_id == bron.id))
    bijlage = result.scalar_one_or_none()
    if bijlage is None:
        raise HTTPException(status_code=404, detail="Geen bijlage gevonden")

    file_path = _safe_path(bijlage.pad)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Bestand niet gevonden op disk")

    # Force download (Content-Disposition: attachment) to prevent inline
    # rendering of potentially dangerous content (e.g. HTML/SVG).
    # Sanitize filename to prevent header injection via control chars.
    safe_filename = (
        bijlage.bestandsnaam.replace('"', "").replace("\r", "").replace("\n", "")
    )
    return FileResponse(
        path=str(file_path),
        filename=safe_filename,
        media_type="application/octet-stream",
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bijlage(
    node_id: uuid.UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    bron = await _get_bron(node_id, db)

    result = await db.execute(select(BronBijlage).where(BronBijlage.bron_id == bron.id))
    bijlage = result.scalar_one_or_none()
    if bijlage is None:
        raise HTTPException(status_code=404, detail="Geen bijlage gevonden")

    file_path = _safe_path(bijlage.pad)
    await db.delete(bijlage)
    # Delete file after DB delete succeeds (commit happens in get_db).
    if file_path.exists():
        file_path.unlink()
