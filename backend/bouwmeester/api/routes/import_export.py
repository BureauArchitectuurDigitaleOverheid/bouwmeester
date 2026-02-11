"""API routes for bulk import and export."""

import asyncio
import io
import logging
import os
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import validate_csv_upload
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.schema.database_backup import (
    DatabaseBackupInfo,
    DatabaseRestoreResult,
)
from bouwmeester.schema.import_export import ImportResult
from bouwmeester.services.archimate_export_service import (
    ArchiMateExportService,
)
from bouwmeester.services.export_service import ExportService
from bouwmeester.services.import_service import ImportService

logger = logging.getLogger(__name__)

MAX_BACKUP_SIZE = 500 * 1024 * 1024  # 500 MB

router = APIRouter(tags=["import-export"])


# ── Import routes ──────────────────────────────────────────────────────


@router.post("/import/politieke-inputs", response_model=ImportResult)
async def import_politieke_inputs(
    file: UploadFile,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> ImportResult:
    """Upload a CSV to bulk-import politieke inputs."""
    content = await validate_csv_upload(file)
    service = ImportService(db)
    return await service.import_politieke_inputs_csv(content)


@router.post("/import/nodes", response_model=ImportResult)
async def import_nodes(
    file: UploadFile,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> ImportResult:
    """Upload a CSV to bulk-import generic nodes."""
    content = await validate_csv_upload(file)
    service = ImportService(db)
    return await service.import_nodes_csv(content)


@router.post("/import/edges", response_model=ImportResult)
async def import_edges(
    file: UploadFile,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> ImportResult:
    """Upload a CSV to bulk-import edges."""
    content = await validate_csv_upload(file)
    service = ImportService(db)
    return await service.import_edges_csv(content)


# ── Export routes ──────────────────────────────────────────────────────


@router.get("/export/nodes")
async def export_nodes(
    current_user: OptionalUser,
    node_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export all nodes as CSV (optionally filtered by node_type)."""
    service = ExportService(db)
    csv_content = await service.export_nodes_csv(node_type=node_type)
    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=nodes.csv"},
    )


@router.get("/export/edges")
async def export_edges(
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export all edges as CSV."""
    service = ExportService(db)
    csv_content = await service.export_edges_csv()
    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=edges.csv"},
    )


@router.get("/export/corpus")
async def export_corpus(
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Export full corpus as JSON (nodes + edges + types)."""
    service = ExportService(db)
    data = await service.export_corpus_json()
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": ("attachment; filename=corpus.json")},
    )


@router.get("/export/archimate")
async def export_archimate(
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export corpus as ArchiMate Exchange Format XML."""
    service = ArchiMateExportService(db)
    xml_content = await service.export_archimate_xml()
    return StreamingResponse(
        io.StringIO(xml_content),
        media_type="application/xml",
        headers={
            "Content-Disposition": ("attachment; filename=bouwmeester-archimate.xml")
        },
    )


# ── Database backup / restore ────────────────────────────────────────


@router.get("/export/database")
async def export_database(
    current_user: OptionalUser,
) -> StreamingResponse:
    """Export full database as pg_dump (optionally age-encrypted)."""
    from bouwmeester.services.database_backup_service import (
        export_database as do_export,
    )

    try:
        file_bytes, filename = await asyncio.to_thread(do_export)
    except Exception:
        logger.exception("Database export failed")
        raise HTTPException(
            status_code=500, detail="Database export mislukt. Zie server logs."
        )

    media_type = (
        "application/octet-stream" if filename.endswith(".age") else "application/gzip"
    )
    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export/database/info", response_model=DatabaseBackupInfo)
async def export_database_info(
    current_user: OptionalUser,
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


@router.post("/import/database", response_model=DatabaseRestoreResult)
async def import_database(
    file: UploadFile,
    current_user: OptionalUser,
) -> DatabaseRestoreResult:
    """Upload a database backup and restore it."""
    from bouwmeester.services.database_backup_service import (
        import_database as do_import,
    )

    content = await file.read()
    if len(content) > MAX_BACKUP_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Bestand te groot (max {MAX_BACKUP_SIZE // 1024 // 1024} MB)",
        )
    try:
        return await asyncio.to_thread(do_import, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception:
        logger.exception("Database import failed")
        raise HTTPException(
            status_code=500, detail="Database import mislukt. Zie server logs."
        )
