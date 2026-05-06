"""API routes for Samenwerkingsverband (programma/werkgroep/...)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_deleted, require_found
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import require_permission
from bouwmeester.models.person import Person
from bouwmeester.models.persoon_samenwerkingsverband import (
    PersoonSamenwerkingsverband,
)
from bouwmeester.models.samenwerkingsverband import Samenwerkingsverband
from bouwmeester.repositories.samenwerkingsverband import (
    SamenwerkingsverbandRepository,
)
from bouwmeester.schema.samenwerkingsverband import (
    PersoonLidmaatschapResponse,
    SamenwerkingsverbandCreate,
    SamenwerkingsverbandDetailResponse,
    SamenwerkingsverbandLidCreate,
    SamenwerkingsverbandLidResponse,
    SamenwerkingsverbandLidUpdate,
    SamenwerkingsverbandResponse,
    SamenwerkingsverbandUpdate,
)
from bouwmeester.services.activity_service import log_activity

router = APIRouter(
    prefix="/samenwerkingsverbanden",
    tags=["samenwerkingsverbanden"],
)


def _to_response(
    verband: Samenwerkingsverband, aantal_leden: int = 0
) -> SamenwerkingsverbandResponse:
    """Bouw een SamenwerkingsverbandResponse zonder de leden-relationship aan
    te raken (vermijdt MissingGreenlet bij lazy-load in async)."""
    return SamenwerkingsverbandResponse(
        id=verband.id,
        naam=verband.naam,
        type=verband.type,
        beschrijving=verband.beschrijving,
        start_datum=verband.start_datum,
        eind_datum=verband.eind_datum,
        created_by_id=verband.created_by_id,
        created_at=verband.created_at,
        updated_at=verband.updated_at,
        aantal_leden=aantal_leden,
    )


def _to_lid_response(
    lid: PersoonSamenwerkingsverband,
) -> SamenwerkingsverbandLidResponse:
    return SamenwerkingsverbandLidResponse(
        id=lid.id,
        samenwerkingsverband_id=lid.samenwerkingsverband_id,
        person_id=lid.person_id,
        person_naam=lid.person.naam if lid.person else "",
        person_functie=lid.person.functie if lid.person else None,
        person_expertise=getattr(lid.person, "expertise", None) if lid.person else None,
        rol=lid.rol,
        start_datum=lid.start_datum,
        eind_datum=lid.eind_datum,
        created_at=lid.created_at,
    )


@router.get("", response_model=list[SamenwerkingsverbandResponse])
async def list_samenwerkingsverbanden(
    current_user: OptionalUser,
    search: str | None = Query(None, max_length=200),
    type: str | None = Query(None, max_length=50),
    actief: bool | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("samenwerkingsverband:read")),
) -> list[SamenwerkingsverbandResponse]:
    repo = SamenwerkingsverbandRepository(db)
    rows = await repo.get_all(
        skip=skip, limit=limit, search=search, type_filter=type, actief=actief
    )
    return [_to_response(v, aantal_leden=count) for v, count in rows]


@router.post(
    "",
    response_model=SamenwerkingsverbandResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_samenwerkingsverband(
    data: SamenwerkingsverbandCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("samenwerkingsverband:create")),
) -> SamenwerkingsverbandResponse:
    repo = SamenwerkingsverbandRepository(db)
    created_by_id = current_user.id if current_user else None
    verband = await repo.create(data, created_by_id=created_by_id)

    await log_activity(
        db,
        current_user,
        None,
        "samenwerkingsverband.created",
        details={
            "samenwerkingsverband_id": str(verband.id),
            "naam": verband.naam,
            "type": verband.type,
        },
    )

    return _to_response(verband, aantal_leden=0)


@router.get(
    "/by-person/{person_id}",
    response_model=list[PersoonLidmaatschapResponse],
)
async def list_for_person(
    person_id: UUID,
    current_user: OptionalUser,
    actief: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("samenwerkingsverband:read")),
) -> list[PersoonLidmaatschapResponse]:
    """Geef alle (actieve) lidmaatschappen voor een persoon."""
    require_found(await db.get(Person, person_id), "Person")
    repo = SamenwerkingsverbandRepository(db)
    rows = await repo.list_for_person(person_id, actief=actief)
    return [
        PersoonLidmaatschapResponse(
            id=lid.id,
            samenwerkingsverband_id=lid.samenwerkingsverband_id,
            samenwerkingsverband_naam=lid.samenwerkingsverband.naam,
            samenwerkingsverband_type=lid.samenwerkingsverband.type,
            rol=lid.rol,
            start_datum=lid.start_datum,
            eind_datum=lid.eind_datum,
        )
        for lid in rows
    ]


@router.get("/{id}", response_model=SamenwerkingsverbandDetailResponse)
async def get_samenwerkingsverband(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("samenwerkingsverband:read")),
) -> SamenwerkingsverbandDetailResponse:
    repo = SamenwerkingsverbandRepository(db)
    verband = require_found(await repo.get(id), "Samenwerkingsverband")
    leden_actief = await repo.list_members(id, actief=True)
    aantal = await repo.count_active_members(id)

    return SamenwerkingsverbandDetailResponse(
        id=verband.id,
        naam=verband.naam,
        type=verband.type,
        beschrijving=verband.beschrijving,
        start_datum=verband.start_datum,
        eind_datum=verband.eind_datum,
        created_by_id=verband.created_by_id,
        created_at=verband.created_at,
        updated_at=verband.updated_at,
        aantal_leden=aantal,
        leden=[_to_lid_response(lid) for lid in leden_actief],
    )


@router.put("/{id}", response_model=SamenwerkingsverbandResponse)
async def update_samenwerkingsverband(
    id: UUID,
    data: SamenwerkingsverbandUpdate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("samenwerkingsverband:update")),
) -> SamenwerkingsverbandResponse:
    repo = SamenwerkingsverbandRepository(db)
    verband = require_found(await repo.update(id, data), "Samenwerkingsverband")

    await log_activity(
        db,
        current_user,
        None,
        "samenwerkingsverband.updated",
        details={"samenwerkingsverband_id": str(verband.id), "naam": verband.naam},
    )

    aantal = await repo.count_active_members(id)
    resp = _to_response(verband, aantal_leden=aantal)
    return resp


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_samenwerkingsverband(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("samenwerkingsverband:delete")),
) -> None:
    repo = SamenwerkingsverbandRepository(db)
    verband = require_found(await repo.get(id), "Samenwerkingsverband")
    naam = verband.naam
    require_deleted(await repo.delete(id), "Samenwerkingsverband")

    await log_activity(
        db,
        current_user,
        None,
        "samenwerkingsverband.deleted",
        details={"samenwerkingsverband_id": str(id), "naam": naam},
    )


# --- Leden ---


@router.get("/{id}/leden", response_model=list[SamenwerkingsverbandLidResponse])
async def list_leden(
    id: UUID,
    current_user: OptionalUser,
    actief: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("samenwerkingsverband:read")),
) -> list[SamenwerkingsverbandLidResponse]:
    repo = SamenwerkingsverbandRepository(db)
    require_found(await repo.get(id), "Samenwerkingsverband")
    leden = await repo.list_members(id, actief=actief)
    return [_to_lid_response(lid) for lid in leden]


@router.post(
    "/{id}/leden",
    response_model=SamenwerkingsverbandLidResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_lid(
    id: UUID,
    data: SamenwerkingsverbandLidCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("samenwerkingsverband:update")),
) -> SamenwerkingsverbandLidResponse:
    verband = require_found(
        await db.get(Samenwerkingsverband, id), "Samenwerkingsverband"
    )
    require_found(await db.get(Person, data.person_id), "Person")

    # Voorkom dubbel actief lidmaatschap met dezelfde startdatum (uniqueconstraint)
    from sqlalchemy import select

    stmt = select(PersoonSamenwerkingsverband).where(
        PersoonSamenwerkingsverband.samenwerkingsverband_id == id,
        PersoonSamenwerkingsverband.person_id == data.person_id,
        PersoonSamenwerkingsverband.eind_datum.is_(None),
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Persoon is al lid van dit samenwerkingsverband",
        )

    lid = PersoonSamenwerkingsverband(
        samenwerkingsverband_id=id,
        person_id=data.person_id,
        rol=data.rol,
        start_datum=data.start_datum,
    )
    db.add(lid)
    await db.flush()
    await db.refresh(lid, attribute_names=["person"])

    await log_activity(
        db,
        current_user,
        None,
        "samenwerkingsverband.lid_added",
        details={
            "samenwerkingsverband_id": str(id),
            "samenwerkingsverband_naam": verband.naam,
            "person_id": str(data.person_id),
        },
    )

    return _to_lid_response(lid)


@router.put(
    "/{id}/leden/{lid_id}",
    response_model=SamenwerkingsverbandLidResponse,
)
async def update_lid(
    id: UUID,
    lid_id: UUID,
    data: SamenwerkingsverbandLidUpdate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("samenwerkingsverband:update")),
) -> SamenwerkingsverbandLidResponse:
    from sqlalchemy import select

    stmt = select(PersoonSamenwerkingsverband).where(
        PersoonSamenwerkingsverband.id == lid_id,
        PersoonSamenwerkingsverband.samenwerkingsverband_id == id,
    )
    lid = require_found((await db.execute(stmt)).scalar_one_or_none(), "Lid")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(lid, key, value)
    await db.flush()
    await db.refresh(lid, attribute_names=["person"])

    verband = await db.get(Samenwerkingsverband, id)
    await log_activity(
        db,
        current_user,
        None,
        "samenwerkingsverband.lid_updated",
        details={
            "samenwerkingsverband_id": str(id),
            "samenwerkingsverband_naam": verband.naam if verband else None,
            "person_id": str(lid.person_id),
            "fields": list(data.model_dump(exclude_unset=True).keys()),
        },
    )

    return _to_lid_response(lid)


@router.delete(
    "/{id}/leden/{lid_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_lid(
    id: UUID,
    lid_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("samenwerkingsverband:update")),
) -> None:
    from sqlalchemy import select

    stmt = select(PersoonSamenwerkingsverband).where(
        PersoonSamenwerkingsverband.id == lid_id,
        PersoonSamenwerkingsverband.samenwerkingsverband_id == id,
    )
    lid = require_found((await db.execute(stmt)).scalar_one_or_none(), "Lid")
    person_id = lid.person_id
    verband = await db.get(Samenwerkingsverband, id)
    await db.delete(lid)
    await db.flush()

    await log_activity(
        db,
        current_user,
        None,
        "samenwerkingsverband.lid_removed",
        details={
            "samenwerkingsverband_id": str(id),
            "samenwerkingsverband_naam": verband.naam if verband else None,
            "person_id": str(person_id),
        },
    )
