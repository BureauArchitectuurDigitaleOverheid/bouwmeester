"""API routes for bulk import and export."""

import io

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import validate_csv_upload
from bouwmeester.core.database import get_db
from bouwmeester.schema.import_export import ImportResult
from bouwmeester.services.archimate_export_service import (
    ArchiMateExportService,
)
from bouwmeester.services.export_service import ExportService
from bouwmeester.services.import_service import ImportService

router = APIRouter(tags=["import-export"])


# ── Import routes ──────────────────────────────────────────────────────


@router.post("/import/politieke-inputs", response_model=ImportResult)
async def import_politieke_inputs(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
) -> ImportResult:
    """Upload a CSV to bulk-import politieke inputs."""
    content = await validate_csv_upload(file)
    service = ImportService(db)
    return await service.import_politieke_inputs_csv(content)


@router.post("/import/nodes", response_model=ImportResult)
async def import_nodes(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
) -> ImportResult:
    """Upload a CSV to bulk-import generic nodes."""
    content = await validate_csv_upload(file)
    service = ImportService(db)
    return await service.import_nodes_csv(content)


@router.post("/import/edges", response_model=ImportResult)
async def import_edges(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
) -> ImportResult:
    """Upload a CSV to bulk-import edges."""
    content = await validate_csv_upload(file)
    service = ImportService(db)
    return await service.import_edges_csv(content)


# ── Export routes ──────────────────────────────────────────────────────


@router.get("/export/nodes")
async def export_nodes(
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
