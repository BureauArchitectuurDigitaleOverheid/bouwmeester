"""API routes for opdrachten (assignments and subsidies)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_deleted, require_found, validate_list
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.org_context import (
    OrgContext,
    check_org_scope,
    check_resource_org_scope,
    get_org_context,
)
from bouwmeester.core.permissions import require_permission
from bouwmeester.repositories.opdracht import OpdrachtRepository
from bouwmeester.schema.opdracht import (
    OpdrachtCreate,
    OpdrachtenSummary,
    OpdrachtNodeCreate,
    OpdrachtNodeResponse,
    OpdrachtResponse,
    OpdrachtUpdate,
)
from bouwmeester.services.activity_service import log_activity
from bouwmeester.services.notification_service import NotificationService
from bouwmeester.services.opdracht_task_service import OpdrachtTaskService
from bouwmeester.utils.financieel import calculate_uitnutting

router = APIRouter(prefix="/opdrachten", tags=["opdrachten"])


@router.get("", response_model=list[OpdrachtResponse])
async def list_opdrachten(
    current_user: OptionalUser,
    begrotingsjaar: int | None = None,
    type: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    instrument_id: UUID | None = None,
    opdrachtnemer_id: UUID | None = None,
    opdrachtgever_id: UUID | None = None,
    verantwoordelijke_id: UUID | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[OpdrachtResponse]:
    repo = OpdrachtRepository(db)
    items = await repo.get_all(
        skip=skip,
        limit=limit,
        begrotingsjaar=begrotingsjaar,
        type=type,
        status=status_filter,
        instrument_id=instrument_id,
        opdrachtnemer_id=opdrachtnemer_id,
        opdrachtgever_id=opdrachtgever_id,
        verantwoordelijke_id=verantwoordelijke_id,
    )
    return validate_list(OpdrachtResponse, items)


@router.get("/summary", response_model=OpdrachtenSummary)
async def get_opdrachten_summary(
    current_user: OptionalUser,
    begrotingsjaar: int | None = None,
    type: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    instrument_id: UUID | None = None,
    opdrachtnemer_id: UUID | None = None,
    opdrachtgever_id: UUID | None = None,
    verantwoordelijke_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> OpdrachtenSummary:
    """Server-side aggregation of opdrachten totals (respects active filters)."""
    repo = OpdrachtRepository(db)
    data = await repo.get_summary(
        begrotingsjaar=begrotingsjaar,
        type=type,
        status=status_filter,
        instrument_id=instrument_id,
        opdrachtnemer_id=opdrachtnemer_id,
        opdrachtgever_id=opdrachtgever_id,
        verantwoordelijke_id=verantwoordelijke_id,
    )
    totaal_budget = data["totaal_budget"]
    totaal_gerealiseerd = data["totaal_gerealiseerd"]
    return OpdrachtenSummary(
        count=data["count"],
        totaal_budget=totaal_budget,
        totaal_gerealiseerd=totaal_gerealiseerd,
        uitnutting_percentage=calculate_uitnutting(totaal_budget, totaal_gerealiseerd),
    )


@router.post(
    "",
    response_model=OpdrachtResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_opdracht(
    data: OpdrachtCreate,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("opdracht:create")),
    org_ctx: OrgContext = Depends(get_org_context),
) -> OpdrachtResponse:
    check_org_scope(data.opdrachtgever_id, org_ctx)
    repo = OpdrachtRepository(db)
    opdracht = await repo.create(data)

    # Activity logging
    await log_activity(
        db,
        current_user,
        actor_id,
        "opdracht.created",
        node_id=opdracht.instrument_id,
        details={
            "opdracht_id": str(opdracht.id),
            "titel": opdracht.titel,
            "type": opdracht.type,
            "status": opdracht.status,
        },
    )

    # Notifications
    actor = current_user.id if current_user else actor_id
    ns = NotificationService(db)
    await ns.notify_opdracht_assigned(opdracht, actor_id=actor)

    # Auto-generate tasks
    await OpdrachtTaskService(db).on_opdracht_created(opdracht)

    return OpdrachtResponse.model_validate(opdracht)


@router.get("/{id}", response_model=OpdrachtResponse)
async def get_opdracht(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> OpdrachtResponse:
    repo = OpdrachtRepository(db)
    opdracht = require_found(await repo.get(id), "Opdracht")
    return OpdrachtResponse.model_validate(opdracht)


@router.put("/{id}", response_model=OpdrachtResponse)
async def update_opdracht(
    id: UUID,
    data: OpdrachtUpdate,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("opdracht:update")),
    org_ctx: OrgContext = Depends(get_org_context),
) -> OpdrachtResponse:
    repo = OpdrachtRepository(db)

    # Capture old state before update
    await check_resource_org_scope(db, "opdracht", id, org_ctx)
    if data.opdrachtgever_id is not None:
        check_org_scope(data.opdrachtgever_id, org_ctx)
    old = await repo.get(id)
    require_found(old, "Opdracht")

    # Reject setting instrument_id to null on non-FCC opdrachten
    if (
        "instrument_id" in data.model_fields_set
        and data.instrument_id is None
        and not old.fcc_id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="instrument_id mag niet null zijn voor reguliere opdrachten",
        )

    old_status = old.status
    old_verantwoordelijke_id = old.verantwoordelijke_id

    opdracht = require_found(await repo.update(id, data), "Opdracht")

    # Determine changed fields for activity details
    changed = data.model_dump(exclude_unset=True)
    await log_activity(
        db,
        current_user,
        actor_id,
        "opdracht.updated",
        node_id=opdracht.instrument_id,
        details={
            "opdracht_id": str(opdracht.id),
            "titel": opdracht.titel,
            "changed_fields": list(changed.keys()),
        },
    )

    # Notifications
    actor = current_user.id if current_user else actor_id
    ns = NotificationService(db)

    if opdracht.verantwoordelijke_id != old_verantwoordelijke_id:
        await ns.notify_opdracht_assigned(opdracht, actor_id=actor)

    if opdracht.status != old_status:
        await ns.notify_opdracht_status_changed(opdracht, old_status, actor_id=actor)
        await OpdrachtTaskService(db).on_status_changed(opdracht, old_status)

    # Auto-flag FCC-linked opdrachten for push
    from bouwmeester.schema.fcc import SyncDirection, SyncStatus

    if opdracht.fcc_id and opdracht.sync_direction != SyncDirection.inbound:
        opdracht.sync_status = SyncStatus.pending_push
        await db.flush()

    return OpdrachtResponse.model_validate(opdracht)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_opdracht(
    id: UUID,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("opdracht:delete")),
    org_ctx: OrgContext = Depends(get_org_context),
) -> None:
    repo = OpdrachtRepository(db)

    # Capture info before deletion for activity log
    await check_resource_org_scope(db, "opdracht", id, org_ctx)
    opdracht = await repo.get(id)
    require_found(opdracht, "Opdracht")
    instrument_id = opdracht.instrument_id
    titel = opdracht.titel

    require_deleted(await repo.delete(id), "Opdracht")

    await log_activity(
        db,
        current_user,
        actor_id,
        "opdracht.deleted",
        node_id=instrument_id,
        details={
            "opdracht_id": str(id),
            "titel": titel,
        },
    )


# --- Node koppelingen ---


@router.post(
    "/{opdracht_id}/koppelingen",
    response_model=OpdrachtNodeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_node_koppeling(
    opdracht_id: UUID,
    data: OpdrachtNodeCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("opdracht:update")),
    org_ctx: OrgContext = Depends(get_org_context),
) -> OpdrachtNodeResponse:
    await check_resource_org_scope(db, "opdracht", opdracht_id, org_ctx)
    repo = OpdrachtRepository(db)
    require_found(await repo.get(opdracht_id), "Opdracht")
    link = await repo.add_node_koppeling(opdracht_id, data)
    return OpdrachtNodeResponse.model_validate(link)


@router.delete(
    "/{opdracht_id}/koppelingen/{koppeling_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_node_koppeling(
    opdracht_id: UUID,
    koppeling_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("opdracht:update")),
    org_ctx: OrgContext = Depends(get_org_context),
) -> None:
    await check_resource_org_scope(db, "opdracht", opdracht_id, org_ctx)
    repo = OpdrachtRepository(db)
    require_deleted(
        await repo.remove_node_koppeling(opdracht_id, koppeling_id), "Koppeling"
    )
