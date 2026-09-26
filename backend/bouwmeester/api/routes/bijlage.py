"""API routes for file attachments on Bron nodes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.authz import requires
from bouwmeester.core.database import get_db
from bouwmeester.core.org_context import (
    OrgContext,
    check_resource_org_scope,
    get_org_context,
)
from bouwmeester.core.storage import (
    BRON_ALLOWED_CONTENT_TYPES,
    blob_available,
    blob_download,
    delete_blob,
    read_upload_content,
    store_upload,
    validate_upload,
)
from bouwmeester.models.bron import Bron
from bouwmeester.models.bron_bijlage import BronBijlage
from bouwmeester.schema.bron import BronBijlageResponse
from bouwmeester.services.activity_service import log_activity

router = APIRouter(prefix="/nodes/{node_id}/bijlage", tags=["bijlage"])


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
    _authz=Depends(requires("node:update", "corpus_node", path_param="node_id")),
) -> BronBijlageResponse:
    """Upload a file attachment to a bron node. Replaces existing attachment."""
    bron = await _get_bron(node_id, db, load_bijlage=True)

    content_type = file.content_type or ""
    content = await read_upload_content(file)
    validate_upload(content, content_type, allowed=BRON_ALLOWED_CONTENT_TYPES)

    # Write new file first (before deleting old one, to avoid data loss
    # on write failure).
    filename, relative_path = await store_upload(
        content,
        file.filename or "bijlage",
        item_id=node_id,
        content_type=content_type,
    )

    # Remove existing bijlage if present (file + DB row).
    if bron.bijlage:
        await delete_blob(bron.bijlage.pad)
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
    org_ctx: OrgContext = Depends(get_org_context),
) -> BronBijlageResponse | None:
    """Get metadata about a bron node's attachment (filename, size, type)."""
    await check_resource_org_scope(db, "corpus_node", node_id, org_ctx)
    bron = await _get_bron(node_id, db)

    result = await db.execute(select(BronBijlage).where(BronBijlage.bron_id == bron.id))
    bijlage = result.scalar_one_or_none()
    if bijlage is None:
        return None
    response = BronBijlageResponse.model_validate(bijlage)
    response.bestand_beschikbaar = await blob_available(bijlage.pad)
    return response


@router.get("/download")
async def download_bijlage(
    node_id: uuid.UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(get_org_context),
) -> Response:
    """Download the file attachment of a bron node."""
    await check_resource_org_scope(db, "corpus_node", node_id, org_ctx)
    bron = await _get_bron(node_id, db)

    result = await db.execute(select(BronBijlage).where(BronBijlage.bron_id == bron.id))
    bijlage = result.scalar_one_or_none()
    if bijlage is None:
        raise HTTPException(status_code=404, detail="Geen bijlage gevonden")

    return await blob_download(
        bijlage.pad,
        bijlage.bestandsnaam,
        bijlage.content_type or "application/octet-stream",
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bijlage(
    node_id: uuid.UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _authz=Depends(requires("node:update", "corpus_node", path_param="node_id")),
) -> None:
    """Delete a bron node's file attachment (DB record and stored file)."""
    bron = await _get_bron(node_id, db)

    result = await db.execute(select(BronBijlage).where(BronBijlage.bron_id == bron.id))
    bijlage = result.scalar_one_or_none()
    if bijlage is None:
        raise HTTPException(status_code=404, detail="Geen bijlage gevonden")

    bijlage_pad = bijlage.pad
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
    await delete_blob(bijlage_pad)
