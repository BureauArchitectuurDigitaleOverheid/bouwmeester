"""API routes for file attachments on Bron nodes."""

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.models.bron import Bron
from bouwmeester.models.bron_bijlage import BronBijlage
from bouwmeester.schema.bron import BronBijlageResponse

router = APIRouter(prefix="/nodes/{node_id}/bijlage", tags=["bijlage"])

BIJLAGEN_ROOT = Path(os.environ.get("BIJLAGEN_ROOT", "/app/bijlagen"))
MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20 MB
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
    "text/plain",
    "image/png",
    "image/jpeg",
}


async def _get_bron(node_id: uuid.UUID, db: AsyncSession) -> Bron:
    result = await db.execute(select(Bron).where(Bron.id == node_id))
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
    bron = await _get_bron(node_id, db)

    content_type = file.content_type or ""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Ongeldig bestandstype: {content_type}. "
                "Toegestaan: PDF, Word, ODT, TXT, PNG, JPEG."
            ),
        )

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        max_mb = MAX_UPLOAD_SIZE // (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"Bestand te groot ({len(content)} bytes). Maximum is {max_mb} MB.",
        )

    # Remove existing bijlage if present
    if bron.bijlage:
        old_path = BIJLAGEN_ROOT / bron.bijlage.pad
        if old_path.exists():
            old_path.unlink()
        await db.delete(bron.bijlage)
        await db.flush()

    # Store on filesystem
    filename = file.filename or "bijlage"
    safe_name = f"{uuid.uuid4().hex}_{filename}"
    dir_path = BIJLAGEN_ROOT / str(node_id)
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / safe_name
    file_path.write_bytes(content)

    relative_path = f"{node_id}/{safe_name}"

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

    file_path = BIJLAGEN_ROOT / bijlage.pad
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Bestand niet gevonden op disk")

    return FileResponse(
        path=str(file_path),
        filename=bijlage.bestandsnaam,
        media_type=bijlage.content_type,
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

    file_path = BIJLAGEN_ROOT / bijlage.pad
    if file_path.exists():
        file_path.unlink()

    await db.delete(bijlage)
