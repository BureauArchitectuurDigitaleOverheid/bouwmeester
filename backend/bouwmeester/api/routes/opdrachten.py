"""API routes for opdrachten (assignments and subsidies)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete as sa_delete
from sqlalchemy.exc import IntegrityError
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
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.repositories.opdracht import OpdrachtRepository
from bouwmeester.repositories.resource_permission import ResourcePermissionRepository
from bouwmeester.schema.opdracht import (
    OpdrachtCreate,
    OpdrachtEenheidCreate,
    OpdrachtEenheidResponse,
    OpdrachtEenheidUpdate,
    OpdrachtenSummary,
    OpdrachtMemberCreate,
    OpdrachtMemberResponse,
    OpdrachtMemberUpdate,
    OpdrachtNodeCreate,
    OpdrachtNodeResponse,
    OpdrachtResponse,
    OpdrachtUpdate,
)
from bouwmeester.services.activity_service import log_activity
from bouwmeester.services.notification_service import NotificationService
from bouwmeester.services.opdracht_matching_service import OpdrachtMatchingService
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
    opdrachtnemer_eenheid_id: UUID | None = None,
    opdrachtgever_id: UUID | None = None,
    verantwoordelijke_id: UUID | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(10_000, ge=1, le=10_000),
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("opdracht:read")),
    org_ctx: OrgContext = Depends(get_org_context),
) -> list[OpdrachtResponse]:
    repo = OpdrachtRepository(db)
    items = await repo.get_all(
        skip=skip,
        limit=limit,
        begrotingsjaar=begrotingsjaar,
        type=type,
        status=status_filter,
        instrument_id=instrument_id,
        opdrachtnemer_eenheid_id=opdrachtnemer_eenheid_id,
        opdrachtgever_id=opdrachtgever_id,
        verantwoordelijke_id=verantwoordelijke_id,
        org_ctx=org_ctx,
    )
    return validate_list(OpdrachtResponse, items)


@router.get("/summary", response_model=OpdrachtenSummary)
async def get_opdrachten_summary(
    current_user: OptionalUser,
    begrotingsjaar: int | None = None,
    type: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    instrument_id: UUID | None = None,
    opdrachtnemer_eenheid_id: UUID | None = None,
    opdrachtgever_id: UUID | None = None,
    verantwoordelijke_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("opdracht:read")),
    org_ctx: OrgContext = Depends(get_org_context),
) -> OpdrachtenSummary:
    """Server-side aggregation of opdrachten totals (respects active filters)."""
    repo = OpdrachtRepository(db)
    data = await repo.get_summary(
        begrotingsjaar=begrotingsjaar,
        type=type,
        status=status_filter,
        instrument_id=instrument_id,
        opdrachtnemer_eenheid_id=opdrachtnemer_eenheid_id,
        opdrachtgever_id=opdrachtgever_id,
        verantwoordelijke_id=verantwoordelijke_id,
        org_ctx=org_ctx,
    )
    totaal_budget = data["totaal_budget"]
    totaal_gerealiseerd = data["totaal_gerealiseerd"]
    return OpdrachtenSummary(
        count=data["count"],
        totaal_budget=totaal_budget,
        totaal_gerealiseerd=totaal_gerealiseerd,
        uitnutting_percentage=calculate_uitnutting(totaal_budget, totaal_gerealiseerd),
    )


@router.post("/match-contacts-bulk")
async def match_contacts_bulk(
    current_user: OptionalUser,
    force: bool = Query(
        False,
        description="Hermatchen voor alle opdrachten, ook met bestaande koppelingen",
    ),
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("opdracht:update")),
) -> dict:
    """Match contacts for opdrachten without linked members/eenheden.

    Pass ?force=true to re-match all opdrachten (including those that
    already have links).
    """
    svc = OpdrachtMatchingService(db)
    result = await svc.match_all_unlinked(force=force)

    await log_activity(
        db,
        current_user,
        None,
        "opdracht.bulk_contacts_matched",
        details=result,
    )

    return result


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
    _perm=Depends(require_permission("opdracht:read")),
    org_ctx: OrgContext = Depends(get_org_context),
) -> OpdrachtResponse:
    await check_resource_org_scope(db, "opdracht", id, org_ctx)
    repo = OpdrachtRepository(db)
    opdracht = require_found(await repo.get(id), "Opdracht")

    # Fetch resource permissions (members + eenheden)
    rp_repo = ResourcePermissionRepository(db)
    all_perms = await rp_repo.list_for_resource("opdracht", id, include_eenheid=True)

    members = [
        OpdrachtMemberResponse(
            opdracht_id=rp.resource_id,
            person_id=rp.person_id,
            person_naam=rp.person.naam if rp.person else "",
            rol=rp.rol,
            source=rp.source,
            ai_confidence=(
                float(rp.ai_confidence) if rp.ai_confidence is not None else None
            ),
            ai_reason=rp.ai_reason,
            created_at=rp.created_at,
        )
        for rp in all_perms
        if rp.person_id is not None
    ]
    eenheden = [
        OpdrachtEenheidResponse(
            opdracht_id=rp.resource_id,
            eenheid_id=rp.organisatie_eenheid_id,
            eenheid_naam=rp.eenheid.naam if rp.eenheid else "",
            rol=rp.rol,
            source=rp.source,
            ai_confidence=(
                float(rp.ai_confidence) if rp.ai_confidence is not None else None
            ),
            ai_reason=rp.ai_reason,
            created_at=rp.created_at,
        )
        for rp in all_perms
        if rp.organisatie_eenheid_id is not None
    ]

    resp = OpdrachtResponse.model_validate(opdracht)
    return resp.model_copy(update={"members": members, "eenheden": eenheden})


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

    # Clean up resource_permission rows (polymorphic FK, no CASCADE)
    await db.execute(
        sa_delete(ResourcePermission).where(
            ResourcePermission.resource_type == "opdracht",
            ResourcePermission.resource_id == id,
        )
    )

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


# ---------------------------------------------------------------------------
# Member management (contactpersonen)
# ---------------------------------------------------------------------------


@router.post(
    "/{id}/members",
    response_model=OpdrachtMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    id: UUID,
    data: OpdrachtMemberCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("opdracht:update")),
    org_ctx: OrgContext = Depends(get_org_context),
) -> OpdrachtMemberResponse:
    await check_resource_org_scope(db, "opdracht", id, org_ctx)
    repo = OpdrachtRepository(db)
    require_found(await repo.get(id), "Opdracht")

    try:
        member = await repo.add_member(id, data.person_id, data.rol)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Persoon is al gekoppeld aan deze opdracht met deze rol",
        )

    await log_activity(
        db,
        current_user,
        None,
        "opdracht_member.added",
        details={
            "opdracht_id": str(id),
            "person_id": str(data.person_id),
            "rol": data.rol,
        },
    )

    return OpdrachtMemberResponse(
        opdracht_id=member.resource_id,
        person_id=member.person_id,
        person_naam=member.person.naam if member.person else "",
        rol=member.rol,
        source=member.source,
        created_at=member.created_at,
    )


@router.delete(
    "/{id}/members/{person_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    id: UUID,
    person_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("opdracht:update")),
    org_ctx: OrgContext = Depends(get_org_context),
) -> None:
    await check_resource_org_scope(db, "opdracht", id, org_ctx)
    repo = OpdrachtRepository(db)
    if not await repo.remove_member(id, person_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contactpersoon niet gevonden",
        )

    await log_activity(
        db,
        current_user,
        None,
        "opdracht_member.removed",
        details={"opdracht_id": str(id), "person_id": str(person_id)},
    )


@router.put(
    "/{id}/members/{person_id}",
    response_model=OpdrachtMemberResponse,
)
async def update_member_role(
    id: UUID,
    person_id: UUID,
    data: OpdrachtMemberUpdate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("opdracht:update")),
    org_ctx: OrgContext = Depends(get_org_context),
) -> OpdrachtMemberResponse:
    await check_resource_org_scope(db, "opdracht", id, org_ctx)
    repo = OpdrachtRepository(db)
    member = await repo.update_member_role(id, person_id, data.rol)
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contactpersoon niet gevonden",
        )

    await log_activity(
        db,
        current_user,
        None,
        "opdracht_member.updated",
        details={
            "opdracht_id": str(id),
            "person_id": str(person_id),
            "rol": data.rol,
        },
    )

    return OpdrachtMemberResponse(
        opdracht_id=member.resource_id,
        person_id=member.person_id,
        person_naam=member.person.naam if member.person else "",
        rol=member.rol,
        source=member.source,
        created_at=member.created_at,
    )


# ---------------------------------------------------------------------------
# Eenheid management (organisatie-eenheden)
# ---------------------------------------------------------------------------


@router.post(
    "/{id}/eenheden",
    response_model=OpdrachtEenheidResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_eenheid(
    id: UUID,
    data: OpdrachtEenheidCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("opdracht:update")),
    org_ctx: OrgContext = Depends(get_org_context),
) -> OpdrachtEenheidResponse:
    await check_resource_org_scope(db, "opdracht", id, org_ctx)
    repo = OpdrachtRepository(db)
    require_found(await repo.get(id), "Opdracht")

    try:
        rp = await repo.add_eenheid(id, data.eenheid_id, data.rol)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Eenheid is al gekoppeld aan deze opdracht met deze rol",
        )

    await log_activity(
        db,
        current_user,
        None,
        "opdracht_eenheid.added",
        details={
            "opdracht_id": str(id),
            "eenheid_id": str(data.eenheid_id),
            "rol": data.rol,
        },
    )

    return OpdrachtEenheidResponse(
        opdracht_id=rp.resource_id,
        eenheid_id=rp.organisatie_eenheid_id,
        eenheid_naam=rp.eenheid.naam if rp.eenheid else "",
        rol=rp.rol,
        source=rp.source,
        created_at=rp.created_at,
    )


@router.delete(
    "/{id}/eenheden/{eenheid_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_eenheid(
    id: UUID,
    eenheid_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("opdracht:update")),
    org_ctx: OrgContext = Depends(get_org_context),
) -> None:
    await check_resource_org_scope(db, "opdracht", id, org_ctx)
    repo = OpdrachtRepository(db)
    if not await repo.remove_eenheid(id, eenheid_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Eenheid niet gevonden",
        )

    await log_activity(
        db,
        current_user,
        None,
        "opdracht_eenheid.removed",
        details={"opdracht_id": str(id), "eenheid_id": str(eenheid_id)},
    )


@router.put(
    "/{id}/eenheden/{eenheid_id}",
    response_model=OpdrachtEenheidResponse,
)
async def update_eenheid_rol(
    id: UUID,
    eenheid_id: UUID,
    data: OpdrachtEenheidUpdate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("opdracht:update")),
    org_ctx: OrgContext = Depends(get_org_context),
) -> OpdrachtEenheidResponse:
    await check_resource_org_scope(db, "opdracht", id, org_ctx)
    repo = OpdrachtRepository(db)
    rp = await repo.update_eenheid_rol(id, eenheid_id, data.rol)
    if rp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Eenheid niet gevonden",
        )

    await log_activity(
        db,
        current_user,
        None,
        "opdracht_eenheid.updated",
        details={
            "opdracht_id": str(id),
            "eenheid_id": str(eenheid_id),
            "rol": data.rol,
        },
    )

    return OpdrachtEenheidResponse(
        opdracht_id=rp.resource_id,
        eenheid_id=rp.organisatie_eenheid_id,
        eenheid_naam=rp.eenheid.naam if rp.eenheid else "",
        rol=rp.rol,
        source=rp.source,
        created_at=rp.created_at,
    )


# ---------------------------------------------------------------------------
# LLM matching (contacten matchen via Vlam)
# ---------------------------------------------------------------------------


@router.post(
    "/{id}/match-contacts",
    response_model=list[OpdrachtMemberResponse | OpdrachtEenheidResponse],
)
async def match_contacts(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("opdracht:update")),
    org_ctx: OrgContext = Depends(get_org_context),
) -> list[OpdrachtMemberResponse | OpdrachtEenheidResponse]:
    """Trigger LLM-based matching of persons/eenheden to this opdracht."""
    await check_resource_org_scope(db, "opdracht", id, org_ctx)
    repo = OpdrachtRepository(db)
    opdracht = require_found(await repo.get(id), "Opdracht")

    svc = OpdrachtMatchingService(db)
    created_rps = await svc.suggest_and_link(opdracht)

    results: list[OpdrachtMemberResponse | OpdrachtEenheidResponse] = []
    for rp in created_rps:
        if rp.person_id is not None:
            results.append(
                OpdrachtMemberResponse(
                    opdracht_id=rp.resource_id,
                    person_id=rp.person_id,
                    person_naam=rp.person.naam if rp.person else "",
                    rol=rp.rol,
                    source=rp.source,
                    ai_confidence=(
                        float(rp.ai_confidence)
                        if rp.ai_confidence is not None
                        else None
                    ),
                    ai_reason=rp.ai_reason,
                    created_at=rp.created_at,
                )
            )
        elif rp.organisatie_eenheid_id is not None:
            results.append(
                OpdrachtEenheidResponse(
                    opdracht_id=rp.resource_id,
                    eenheid_id=rp.organisatie_eenheid_id,
                    eenheid_naam=rp.eenheid.naam if rp.eenheid else "",
                    rol=rp.rol,
                    source=rp.source,
                    ai_confidence=(
                        float(rp.ai_confidence)
                        if rp.ai_confidence is not None
                        else None
                    ),
                    ai_reason=rp.ai_reason,
                    created_at=rp.created_at,
                )
            )

    await log_activity(
        db,
        current_user,
        None,
        "opdracht.contacts_matched",
        details={
            "opdracht_id": str(id),
            "matches_created": len(results),
        },
    )

    return results
