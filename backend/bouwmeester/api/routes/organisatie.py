"""API routes for organisatie-eenheden (organizational hierarchy)."""

from collections import defaultdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_found
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.org_context import OrgContext, get_org_context
from bouwmeester.core.permissions import (
    PermissionContext,
    check_resource_permission,
    require_permission,
)
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.repositories.organisatie_eenheid import OrganisatieEenheidRepository
from bouwmeester.repositories.resource_permission import ResourcePermissionRepository
from bouwmeester.schema.organisatie_eenheid import (
    OrganisatieEenheidCreate,
    OrganisatieEenheidPersonenGroup,
    OrganisatieEenheidResponse,
    OrganisatieEenheidTreeNode,
    OrganisatieEenheidUpdate,
    OrgManagerRecord,
    OrgNaamRecord,
    OrgParentRecord,
)
from bouwmeester.schema.person import PersonResponse
from bouwmeester.services.activity_service import log_activity
from bouwmeester.services.mention_helper import sync_and_notify_mentions

router = APIRouter(prefix="/organisatie", tags=["organisatie"])


async def _check_eenheid_write_access(
    db: AsyncSession,
    eenheid_id: UUID,
    perm_ctx: PermissionContext,
    org_ctx: OrgContext,
) -> None:
    """Allow update/delete on an eenheid that is either in scope or owned.

    A user with org:manage may mutate any eenheid within their org scope
    (the regular ministry-admin / unit-manager case). Editors who created
    a stakeholder eenheid outside their scope are granted an "eigenaar"
    resource-permission at create-time and may mutate it via that path.
    Raises 403 otherwise.

    TOOI/synthetische rijen zijn read-only behalve voor super_admin —
    die kennen we als bron != 'handmatig'. Mutaties op die rijen worden
    geblokkeerd zodat een TOOI-sync ze niet vermalen worden door
    handmatige bewerkingen.
    """
    if perm_ctx.is_super_admin:
        return

    # Read-only check op niet-handmatige bron
    eenheid = (
        await db.execute(
            select(OrganisatieEenheid.bron).where(OrganisatieEenheid.id == eenheid_id)
        )
    ).scalar_one_or_none()
    if eenheid is not None and eenheid != "handmatig":
        raise HTTPException(
            status_code=403,
            detail=(
                f"Deze organisatie-eenheid is read-only (bron='{eenheid}'). "
                "TOOI/scrape/synthetische rijen worden door de sync beheerd; "
                "alleen super_admin kan ze handmatig wijzigen."
            ),
        )

    all_visible = set(org_ctx.visible_eenheid_ids) | set(org_ctx.shared_eenheid_ids)
    if org_ctx.is_admin or eenheid_id in all_visible:
        return
    if perm_ctx.person_id is not None and await check_resource_permission(
        db,
        perm_ctx.person_id,
        "organisatie_eenheid",
        eenheid_id,
        "org:manage",
    ):
        return
    raise HTTPException(
        status_code=403, detail="Geen toegang tot deze organisatie-eenheid"
    )


async def _enrich_with_managers(
    repo: OrganisatieEenheidRepository,
    responses: list[OrganisatieEenheidResponse],
) -> None:
    """Populate manager/manager_id on responses from person_role."""
    eenheid_ids = [r.id for r in responses]
    managers_map = await repo.get_unit_managers_batch(eenheid_ids)
    for resp in responses:
        mgr = managers_map.get(resp.id)
        if mgr:
            resp.manager = PersonResponse.model_validate(mgr)
            resp.manager_id = mgr.id
        else:
            resp.manager = None
            resp.manager_id = None


def _build_tree(
    all_items: list[OrganisatieEenheidResponse],
    personen_counts: dict[UUID, int],
    parent_id: UUID | None = None,
) -> list[OrganisatieEenheidTreeNode]:
    """Build a tree from a flat list.

    Uses the legacy parent_id column which is dual-written by the repository
    to stay in sync with the temporal OrganisatieEenheidParent records.
    """
    children = [item for item in all_items if item.parent_id == parent_id]
    nodes: list[OrganisatieEenheidTreeNode] = []
    for item in sorted(children, key=lambda x: x.naam):
        sub = _build_tree(all_items, personen_counts, item.id)
        nodes.append(
            OrganisatieEenheidTreeNode(
                **item.model_dump(),
                children=sub,
                personen_count=personen_counts.get(item.id, 0),
                children_count=len(sub),
                has_children=bool(sub),
            )
        )
    return nodes


@router.get(
    "",
    response_model=list[OrganisatieEenheidResponse] | list[OrganisatieEenheidTreeNode],
)
async def list_organisatie(
    current_user: OptionalUser,
    format: str = Query("flat", pattern="^(flat|tree)$"),
    include_historisch: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> list[OrganisatieEenheidResponse] | list[OrganisatieEenheidTreeNode]:
    """List org units as flat list or hierarchical tree (format=flat|tree).

    Met `include_historisch=true` worden ook rijen met `geldig_tot != NULL`
    meegenomen — bv. opgeheven gemeenten, oude ministeries, of TOOI-rijen
    die uit de feed verdwenen zijn. UI gebruikt dit voor de
    'Toon historisch'-toggle.
    """
    repo = OrganisatieEenheidRepository(db)
    # Hoge limit om alle TOOI-rijen mee te krijgen (~1500). Performance is OK
    # tot ~5k; bij meer schalen we naar paginated of lazy.
    items = await repo.get_all(limit=10000, active_only=not include_historisch)
    flat = [OrganisatieEenheidResponse.model_validate(item) for item in items]
    await _enrich_with_managers(repo, flat)

    if format == "tree":
        personen_counts = await repo.count_personen_batch([item.id for item in items])
        return _build_tree(flat, personen_counts)

    return flat


@router.get(
    "/tree-children",
    response_model=list[OrganisatieEenheidTreeNode],
)
async def get_tree_children(
    current_user: OptionalUser,
    parent_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[OrganisatieEenheidTreeNode]:
    """Geef directe children van een eenheid (of root als parent_id ontbreekt).

    Wordt gebruikt voor lazy-load van de boom: bij uitvouwen van een node
    haalt de UI alleen de directe children op (met counts), niet de hele
    sub-boom. Levert per child `personen_count`, `children_count` en
    `has_children` zodat de UI direct kan tonen welke nodes nog
    uitklapbaar zijn.
    """
    repo = OrganisatieEenheidRepository(db)
    units = await repo.get_by_parent(parent_id)
    responses = [OrganisatieEenheidResponse.model_validate(u) for u in units]
    await _enrich_with_managers(repo, responses)

    ids = [r.id for r in responses]
    personen_counts = await repo.count_personen_batch(ids)
    children_counts = await repo.count_children_batch(ids)

    return [
        OrganisatieEenheidTreeNode(
            **r.model_dump(),
            children=[],  # lazy: niet meegestuurd
            personen_count=personen_counts.get(r.id, 0),
            children_count=children_counts.get(r.id, 0),
            has_children=children_counts.get(r.id, 0) > 0,
        )
        for r in sorted(responses, key=lambda x: x.naam)
    ]


@router.get("/search", response_model=list[OrganisatieEenheidResponse])
async def search_organisatie(
    current_user: OptionalUser,
    q: str = Query("", min_length=0, max_length=500),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> list[OrganisatieEenheidResponse]:
    """Search org units by name."""
    if not q.strip():
        return []
    repo = OrganisatieEenheidRepository(db)
    units = await repo.search(q.strip(), limit=limit)
    results = [OrganisatieEenheidResponse.model_validate(u) for u in units]
    await _enrich_with_managers(repo, results)
    return results


@router.get("/managed-by/{person_id}", response_model=list[OrganisatieEenheidResponse])
async def get_managed_eenheden(
    person_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> list[OrganisatieEenheidResponse]:
    """Get all eenheden where person_id is the manager."""
    repo = OrganisatieEenheidRepository(db)
    eenheden = await repo.get_by_manager(person_id)
    results = [OrganisatieEenheidResponse.model_validate(e) for e in eenheden]
    await _enrich_with_managers(repo, results)
    return results


@router.post(
    "", response_model=OrganisatieEenheidResponse, status_code=status.HTTP_201_CREATED
)
async def create_organisatie(
    data: OrganisatieEenheidCreate,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(
        require_permission("org:create", "org:manage")
    ),
) -> OrganisatieEenheidResponse:
    """Create a new org unit, optionally under a parent.

    Anyone with org:manage may pick any parent (or none) — stakeholder
    eenheden often live outside the caller's own ministry. The aanmaker
    is granted an eigenaar resource-permission so they can edit/delete
    their creation later, even if it falls outside their org scope.
    """
    repo = OrganisatieEenheidRepository(db)
    if data.parent_id is not None:
        require_found(await repo.get(data.parent_id), "Parent eenheid")
    eenheid = await repo.create(data)

    if perm_ctx.person_id is not None and not perm_ctx.is_super_admin:
        await ResourcePermissionRepository(db).create_permission(
            person_id=perm_ctx.person_id,
            resource_type="organisatie_eenheid",
            resource_id=eenheid.id,
            rol="eigenaar",
        )

    await sync_and_notify_mentions(
        db,
        "organisatie",
        eenheid.id,
        data.beschrijving,
        eenheid.naam,
    )

    await log_activity(
        db,
        current_user,
        actor_id,
        "organisatie.created",
        details={"organisatie_id": str(eenheid.id), "naam": eenheid.naam},
    )

    resp = OrganisatieEenheidResponse.model_validate(eenheid)
    await _enrich_with_managers(repo, [resp])
    return resp


@router.get("/{id}", response_model=OrganisatieEenheidResponse)
async def get_organisatie(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> OrganisatieEenheidResponse:
    """Get a single org unit by ID."""
    repo = OrganisatieEenheidRepository(db)
    eenheid = require_found(await repo.get(id), "Eenheid")
    resp = OrganisatieEenheidResponse.model_validate(eenheid)
    await _enrich_with_managers(repo, [resp])
    return resp


@router.put("/{id}", response_model=OrganisatieEenheidResponse)
async def update_organisatie(
    id: UUID,
    data: OrganisatieEenheidUpdate,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(
        require_permission("org:create", "org:manage")
    ),
    org_ctx: OrgContext = Depends(get_org_context),
) -> OrganisatieEenheidResponse:
    """Update an org unit. Detects circular parent references."""
    await _check_eenheid_write_access(db, id, perm_ctx, org_ctx)
    repo = OrganisatieEenheidRepository(db)

    # Cycle detection for parent_id changes
    if data.parent_id is not None:
        if data.parent_id == id:
            raise HTTPException(400, "Eenheid kan niet zijn eigen parent zijn")
        descendants = await repo.get_descendant_ids(id)
        if data.parent_id in descendants:
            raise HTTPException(400, "Circulaire parent-relatie gedetecteerd")

    eenheid = require_found(await repo.update(id, data), "Eenheid")

    await sync_and_notify_mentions(
        db,
        "organisatie",
        eenheid.id,
        eenheid.beschrijving,
        eenheid.naam,
    )

    await log_activity(
        db,
        current_user,
        actor_id,
        "organisatie.updated",
        details={"organisatie_id": str(eenheid.id), "naam": eenheid.naam},
    )

    resp = OrganisatieEenheidResponse.model_validate(eenheid)
    await _enrich_with_managers(repo, [resp])
    return resp


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organisatie(
    id: UUID,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(
        require_permission("org:create", "org:manage")
    ),
    org_ctx: OrgContext = Depends(get_org_context),
) -> None:
    """Delete an org unit. Fails if it has children or members."""
    await _check_eenheid_write_access(db, id, perm_ctx, org_ctx)
    repo = OrganisatieEenheidRepository(db)
    eenheid = require_found(await repo.get(id), "Eenheid")
    if await repo.has_children(id):
        raise HTTPException(
            status_code=409,
            detail="Kan niet verwijderen: eenheid heeft subeenheden",
        )
    if await repo.has_personen(id):
        raise HTTPException(
            status_code=409,
            detail="Kan niet verwijderen: eenheid heeft personen",
        )
    eenheid_naam = eenheid.naam
    await repo.delete(id)

    await log_activity(
        db,
        current_user,
        actor_id,
        "organisatie.deleted",
        details={"organisatie_id": str(id), "naam": eenheid_naam},
    )


@router.get("/{id}/history/namen", response_model=list[OrgNaamRecord])
async def get_naam_history(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> list[OrgNaamRecord]:
    """Get temporal history of name changes for an org unit."""
    repo = OrganisatieEenheidRepository(db)
    require_found(await repo.get(id), "Eenheid")
    records = await repo.get_naam_history(id)
    return [OrgNaamRecord.model_validate(r) for r in records]


@router.get("/{id}/history/parents", response_model=list[OrgParentRecord])
async def get_parent_history(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> list[OrgParentRecord]:
    """Get temporal history of parent changes for an org unit."""
    repo = OrganisatieEenheidRepository(db)
    require_found(await repo.get(id), "Eenheid")
    records = await repo.get_parent_history(id)
    return [OrgParentRecord.model_validate(r) for r in records]


@router.get("/{id}/history/managers", response_model=list[OrgManagerRecord])
async def get_manager_history(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> list[OrgManagerRecord]:
    """Get temporal history of manager changes from person_role."""
    repo = OrganisatieEenheidRepository(db)
    require_found(await repo.get(id), "Eenheid")
    records = await repo.get_manager_history(id)
    return [
        OrgManagerRecord(
            id=r.id,
            manager_id=r.person_id,
            manager=PersonResponse.model_validate(r.person) if r.person else None,
            geldig_van=r.start_datum,
            geldig_tot=r.eind_datum,
        )
        for r in records
    ]


@router.get(
    "/{id}/personen",
    response_model=list[PersonResponse] | OrganisatieEenheidPersonenGroup,
)
async def get_organisatie_personen(
    id: UUID,
    current_user: OptionalUser,
    recursive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> list[PersonResponse] | OrganisatieEenheidPersonenGroup:
    """Get people in an org unit.

    Use recursive=true for grouped tree of all descendants.
    """
    repo = OrganisatieEenheidRepository(db)
    require_found(await repo.get(id), "Eenheid")

    if not recursive:
        personen = await repo.get_personen(id)
        return [PersonResponse.model_validate(p) for p in personen]

    # Recursive mode: get all descendants and build grouped tree
    descendant_ids = await repo.get_descendant_ids(id)
    all_units = await repo.get_units_by_ids(descendant_ids)
    personen_with_units = await repo.get_personen_for_units(descendant_ids)

    # Pre-fetch all managers for the descendant tree
    managers_map = await repo.get_unit_managers_batch(descendant_ids)

    # Index people by unit ID
    personen_by_unit: dict[UUID, list[PersonResponse]] = defaultdict(list)
    for person, unit_id in personen_with_units:
        personen_by_unit[unit_id].append(PersonResponse.model_validate(person))

    # Index units by ID
    units_by_id = {u.id: u for u in all_units}

    def build_group(unit_id: UUID) -> OrganisatieEenheidPersonenGroup:
        """Build a grouped tree.

        Uses the legacy parent_id column which is dual-written by the
        repository to stay in sync with temporal parent records.
        """
        unit = units_by_id[unit_id]
        resp = OrganisatieEenheidResponse.model_validate(unit)
        mgr = managers_map.get(unit_id)
        if mgr:
            resp.manager = PersonResponse.model_validate(mgr)
            resp.manager_id = mgr.id
        else:
            resp.manager = None
            resp.manager_id = None
        direct_children = sorted(
            [u for u in all_units if u.parent_id == unit_id],
            key=lambda u: u.naam,
        )
        return OrganisatieEenheidPersonenGroup(
            eenheid=resp,
            personen=personen_by_unit.get(unit_id, []),
            children=[build_group(c.id) for c in direct_children],
        )

    return build_group(id)
