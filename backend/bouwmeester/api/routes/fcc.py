"""API routes for FCC (Fortes Change Cloud) sync management."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.api.deps import require_found
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import require_permission
from bouwmeester.models.fcc_sync_log import FccSyncLog
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.schema.fcc import (
    FccConflictResolution,
    FccConflictResolveRequest,
    FccSchemaResponse,
    FccSyncLogResponse,
    FccSyncTriggerResponse,
    SyncStatus,
)
from bouwmeester.schema.opdracht import OpdrachtResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fcc", tags=["fcc"])


@router.post(
    "/sync/trigger",
    response_model=FccSyncTriggerResponse,
)
async def trigger_sync(
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("fcc:sync")),
) -> FccSyncTriggerResponse:
    """Trigger a manual FCC sync cycle (pull, and push if enabled)."""
    from bouwmeester.services.fcc_import_service import FccImportService

    import_service = FccImportService(db)
    pull_count = await import_service.poll_and_import()

    push_count = 0
    if await import_service.is_push_enabled():
        from bouwmeester.services.fcc_export_service import FccExportService

        export_service = FccExportService(db)
        push_count = await export_service.push_pending()

    return FccSyncTriggerResponse(pulled=pull_count, pushed=push_count)


@router.get(
    "/sync/logs",
    response_model=list[FccSyncLogResponse],
)
async def list_sync_logs(
    current_user: OptionalUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    opdracht_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("fcc:sync")),
) -> list[FccSyncLogResponse]:
    """List FCC sync audit log entries."""
    stmt = select(FccSyncLog).order_by(FccSyncLog.created_at.desc())
    if opdracht_id is not None:
        stmt = stmt.where(FccSyncLog.opdracht_id == opdracht_id)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return [FccSyncLogResponse.model_validate(row) for row in result.scalars().all()]


@router.get(
    "/schema",
    response_model=FccSchemaResponse,
)
async def get_fcc_schema(
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("fcc:sync")),
) -> FccSchemaResponse:
    """Discover available FCC OData entity sets via $metadata."""
    from bouwmeester.services.fcc_import_service import FccImportService

    service = FccImportService(db)
    client = await service.get_client()
    if client is None:
        return FccSchemaResponse(entity_sets={})
    async with client:
        metadata = await client.discover_metadata()
    return FccSchemaResponse(entity_sets=metadata.get("entity_sets", {}))


@router.get(
    "/conflicts",
    response_model=list[OpdrachtResponse],
)
async def list_conflicts(
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("fcc:sync")),
) -> list[OpdrachtResponse]:
    """List opdrachten with FCC sync conflicts."""
    stmt = (
        select(Opdracht)
        .where(Opdracht.sync_status == SyncStatus.conflict)
        .options(selectinload(Opdracht.node_koppelingen))
        .order_by(Opdracht.updated_at.desc())
    )
    result = await db.execute(stmt)
    return [OpdrachtResponse.model_validate(row) for row in result.scalars().all()]


@router.post(
    "/conflicts/{opdracht_id}/resolve",
    response_model=OpdrachtResponse,
)
async def resolve_conflict(
    opdracht_id: UUID,
    data: FccConflictResolveRequest,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("fcc:sync")),
) -> OpdrachtResponse:
    """Resolve an FCC sync conflict for an opdracht."""
    from bouwmeester.repositories.opdracht import OpdrachtRepository
    from bouwmeester.services.fcc_export_service import FccExportService
    from bouwmeester.services.fcc_import_service import FccImportService

    repo = OpdrachtRepository(db)
    opdracht = require_found(await repo.get(opdracht_id), "Opdracht")

    if opdracht.sync_status != SyncStatus.conflict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Opdracht heeft geen sync conflict",
        )

    if data.resolution == FccConflictResolution.use_ours:
        # Push our version to FCC (requires push to be enabled)
        if not await FccImportService(db).is_push_enabled():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="FCC push is niet ingeschakeld",
            )
        export_service = FccExportService(db)
        await export_service.push_single(opdracht_id, force=True)
    else:
        # Pull FCC version and overwrite ours
        import_service = FccImportService(db)
        await import_service.pull_single(opdracht_id)

    # Re-fetch to pick up sync state changes
    opdracht = require_found(await repo.get(opdracht_id), "Opdracht")
    return OpdrachtResponse.model_validate(opdracht)


@router.post(
    "/opdrachten/{opdracht_id}/push",
    response_model=OpdrachtResponse,
)
async def push_opdracht(
    opdracht_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("fcc:sync")),
) -> OpdrachtResponse:
    """Push a single opdracht to FCC (requires FCC_PUSH_ENABLED)."""
    from bouwmeester.repositories.opdracht import OpdrachtRepository
    from bouwmeester.services.fcc_import_service import FccImportService

    import_service = FccImportService(db)
    if not await import_service.is_push_enabled():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="FCC push is niet ingeschakeld",
        )

    from bouwmeester.services.fcc_export_service import FccExportService

    repo = OpdrachtRepository(db)
    opdracht = require_found(await repo.get(opdracht_id), "Opdracht")

    export_service = FccExportService(db)
    await export_service.push_single(opdracht_id)

    # Re-fetch to pick up sync state changes
    opdracht = require_found(await repo.get(opdracht_id), "Opdracht")
    return OpdrachtResponse.model_validate(opdracht)
