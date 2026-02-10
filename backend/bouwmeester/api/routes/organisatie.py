"""API routes for organisatie-eenheden (organizational hierarchy)."""

from collections import defaultdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_found
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.repositories.organisatie_eenheid import OrganisatieEenheidRepository
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
from bouwmeester.services.activity_service import (
    ActivityService,
    resolve_actor_id,
    resolve_actor_naam,
)
from bouwmeester.services.mention_helper import sync_and_notify_mentions

router = APIRouter(prefix="/organisatie", tags=["organisatie"])


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
    return [
        OrganisatieEenheidTreeNode(
            **item.model_dump(),
            children=_build_tree(all_items, personen_counts, item.id),
            personen_count=personen_counts.get(item.id, 0),
        )
        for item in sorted(children, key=lambda x: x.naam)
    ]


@router.get(
    "",
    response_model=list[OrganisatieEenheidResponse] | list[OrganisatieEenheidTreeNode],
)
async def list_organisatie(
    current_user: OptionalUser,
    format: str = Query("flat", pattern="^(flat|tree)$"),
    db: AsyncSession = Depends(get_db),
) -> list[OrganisatieEenheidResponse] | list[OrganisatieEenheidTreeNode]:
    repo = OrganisatieEenheidRepository(db)
    items = await repo.get_all()
    flat = [OrganisatieEenheidResponse.model_validate(item) for item in items]

    if format == "tree":
        personen_counts: dict[UUID, int] = {}
        for item in items:
            personen_counts[item.id] = await repo.count_personen(item.id)
        return _build_tree(flat, personen_counts)

    return flat


@router.get("/search", response_model=list[OrganisatieEenheidResponse])
async def search_organisatie(
    current_user: OptionalUser,
    q: str = Query("", min_length=0, max_length=500),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> list[OrganisatieEenheidResponse]:
    if not q.strip():
        return []
    repo = OrganisatieEenheidRepository(db)
    units = await repo.search(q.strip(), limit=limit)
    return [OrganisatieEenheidResponse.model_validate(u) for u in units]


@router.get("/managed-by/{person_id}", response_model=list[OrganisatieEenheidResponse])
async def get_managed_eenheden(
    person_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> list[OrganisatieEenheidResponse]:
    """Get all eenheden where person_id is the manager."""
    repo = OrganisatieEenheidRepository(db)
    eenheden = await repo.get_by_manager(person_id)
    return [OrganisatieEenheidResponse.model_validate(e) for e in eenheden]


@router.post(
    "", response_model=OrganisatieEenheidResponse, status_code=status.HTTP_201_CREATED
)
async def create_organisatie(
    data: OrganisatieEenheidCreate,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> OrganisatieEenheidResponse:
    repo = OrganisatieEenheidRepository(db)
    if data.parent_id is not None:
        require_found(await repo.get(data.parent_id), "Parent eenheid")
    eenheid = await repo.create(data)

    await sync_and_notify_mentions(
        db,
        "organisatie",
        eenheid.id,
        data.beschrijving,
        eenheid.naam,
    )

    await ActivityService(db).log_event(
        "organisatie.created",
        actor_id=resolve_actor_id(current_user, actor_id),
        actor_naam=resolve_actor_naam(current_user),
        details={"organisatie_id": str(eenheid.id), "naam": eenheid.naam},
    )

    return OrganisatieEenheidResponse.model_validate(eenheid)


@router.get("/{id}", response_model=OrganisatieEenheidResponse)
async def get_organisatie(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> OrganisatieEenheidResponse:
    repo = OrganisatieEenheidRepository(db)
    eenheid = require_found(await repo.get(id), "Eenheid")
    return OrganisatieEenheidResponse.model_validate(eenheid)


@router.put("/{id}", response_model=OrganisatieEenheidResponse)
async def update_organisatie(
    id: UUID,
    data: OrganisatieEenheidUpdate,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> OrganisatieEenheidResponse:
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

    await ActivityService(db).log_event(
        "organisatie.updated",
        actor_id=resolve_actor_id(current_user, actor_id),
        actor_naam=resolve_actor_naam(current_user),
        details={"organisatie_id": str(eenheid.id), "naam": eenheid.naam},
    )

    return OrganisatieEenheidResponse.model_validate(eenheid)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organisatie(
    id: UUID,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> None:
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

    await ActivityService(db).log_event(
        "organisatie.deleted",
        actor_id=resolve_actor_id(current_user, actor_id),
        actor_naam=resolve_actor_naam(current_user),
        details={"organisatie_id": str(id), "naam": eenheid_naam},
    )


@router.get("/{id}/history/namen", response_model=list[OrgNaamRecord])
async def get_naam_history(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> list[OrgNaamRecord]:
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
    repo = OrganisatieEenheidRepository(db)
    require_found(await repo.get(id), "Eenheid")
    records = await repo.get_manager_history(id)
    return [OrgManagerRecord.model_validate(r) for r in records]


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
    repo = OrganisatieEenheidRepository(db)
    require_found(await repo.get(id), "Eenheid")

    if not recursive:
        personen = await repo.get_personen(id)
        return [PersonResponse.model_validate(p) for p in personen]

    # Recursive mode: get all descendants and build grouped tree
    descendant_ids = await repo.get_descendant_ids(id)
    all_units = await repo.get_units_by_ids(descendant_ids)
    personen_with_units = await repo.get_personen_for_units(descendant_ids)

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
        direct_children = sorted(
            [u for u in all_units if u.parent_id == unit_id],
            key=lambda u: u.naam,
        )
        return OrganisatieEenheidPersonenGroup(
            eenheid=OrganisatieEenheidResponse.model_validate(unit),
            personen=personen_by_unit.get(unit_id, []),
            children=[build_group(c.id) for c in direct_children],
        )

    return build_group(id)
