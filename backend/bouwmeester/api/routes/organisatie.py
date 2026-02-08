"""API routes for organisatie-eenheden (organizational hierarchy)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import get_db
from bouwmeester.repositories.organisatie_eenheid import OrganisatieEenheidRepository
from bouwmeester.schema.organisatie_eenheid import (
    OrganisatieEenheidCreate,
    OrganisatieEenheidPersonenGroup,
    OrganisatieEenheidResponse,
    OrganisatieEenheidTreeNode,
    OrganisatieEenheidUpdate,
)
from bouwmeester.schema.person import PersonResponse
from bouwmeester.services.mention_service import MentionService
from bouwmeester.services.notification_service import NotificationService

router = APIRouter(prefix="/organisatie", tags=["organisatie"])


def _build_tree(
    all_items: list[OrganisatieEenheidResponse],
    personen_counts: dict[UUID, int],
    parent_id: UUID | None = None,
) -> list[OrganisatieEenheidTreeNode]:
    """Build a tree from a flat list."""
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
    q: str = Query("", min_length=0),
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
    db: AsyncSession = Depends(get_db),
) -> OrganisatieEenheidResponse:
    repo = OrganisatieEenheidRepository(db)
    if data.parent_id is not None:
        parent = await repo.get(data.parent_id)
        if parent is None:
            raise HTTPException(status_code=404, detail="Parent eenheid not found")
    eenheid = await repo.create(data)

    # Sync mentions from beschrijving
    if data.beschrijving:
        mention_svc = MentionService(db)
        new_mentions = await mention_svc.sync_mentions(
            "organisatie", eenheid.id, data.beschrijving, None
        )
        notif_svc = NotificationService(db)
        for m in new_mentions:
            if m.mention_type == "person":
                await notif_svc.notify_mention(
                    m.target_id,
                    "organisatie",
                    eenheid.naam,
                )

    return OrganisatieEenheidResponse.model_validate(eenheid)


@router.get("/{id}", response_model=OrganisatieEenheidResponse)
async def get_organisatie(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> OrganisatieEenheidResponse:
    repo = OrganisatieEenheidRepository(db)
    eenheid = await repo.get(id)
    if eenheid is None:
        raise HTTPException(status_code=404, detail="Eenheid not found")
    return OrganisatieEenheidResponse.model_validate(eenheid)


@router.put("/{id}", response_model=OrganisatieEenheidResponse)
async def update_organisatie(
    id: UUID,
    data: OrganisatieEenheidUpdate,
    db: AsyncSession = Depends(get_db),
) -> OrganisatieEenheidResponse:
    repo = OrganisatieEenheidRepository(db)
    eenheid = await repo.update(id, data)
    if eenheid is None:
        raise HTTPException(status_code=404, detail="Eenheid not found")

    # Sync mentions from beschrijving
    if data.beschrijving is not None:
        mention_svc = MentionService(db)
        new_mentions = await mention_svc.sync_mentions(
            "organisatie", eenheid.id, data.beschrijving, None
        )
        notif_svc = NotificationService(db)
        for m in new_mentions:
            if m.mention_type == "person":
                await notif_svc.notify_mention(
                    m.target_id,
                    "organisatie",
                    eenheid.naam,
                )

    return OrganisatieEenheidResponse.model_validate(eenheid)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organisatie(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = OrganisatieEenheidRepository(db)
    eenheid = await repo.get(id)
    if eenheid is None:
        raise HTTPException(status_code=404, detail="Eenheid not found")
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
    await repo.delete(id)


@router.get("/{id}/personen")
async def get_organisatie_personen(
    id: UUID,
    recursive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> list[PersonResponse] | OrganisatieEenheidPersonenGroup:
    repo = OrganisatieEenheidRepository(db)
    eenheid = await repo.get(id)
    if eenheid is None:
        raise HTTPException(status_code=404, detail="Eenheid not found")

    if not recursive:
        personen = await repo.get_personen(id)
        return [PersonResponse.model_validate(p) for p in personen]

    # Recursive mode: get all descendants and build grouped tree
    descendant_ids = await repo.get_descendant_ids(id)
    all_units = await repo.get_units_by_ids(descendant_ids)
    all_personen = await repo.get_personen_for_units(descendant_ids)

    # Index people by unit ID
    personen_by_unit: dict[UUID, list[PersonResponse]] = {}
    for p in all_personen:
        uid = p.organisatie_eenheid_id
        if uid not in personen_by_unit:
            personen_by_unit[uid] = []
        personen_by_unit[uid].append(PersonResponse.model_validate(p))

    # Index units by ID
    units_by_id = {u.id: u for u in all_units}

    def build_group(unit_id: UUID) -> OrganisatieEenheidPersonenGroup:
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
