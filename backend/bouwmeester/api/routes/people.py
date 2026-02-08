"""API routes for people."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.api.deps import require_deleted, require_found
from bouwmeester.core.database import get_db
from bouwmeester.models.node_stakeholder import NodeStakeholder
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.task import Task
from bouwmeester.repositories.person import PersonRepository
from bouwmeester.schema.person import (
    PersonCreate,
    PersonDetailResponse,
    PersonOrganisatieCreate,
    PersonOrganisatieResponse,
    PersonOrganisatieUpdate,
    PersonResponse,
    PersonStakeholderNode,
    PersonSummaryResponse,
    PersonTaskSummary,
    PersonUpdate,
)

router = APIRouter(prefix="/people", tags=["people"])


@router.get("", response_model=list[PersonResponse])
async def list_people(
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
) -> list[PersonResponse]:
    repo = PersonRepository(db)
    people = await repo.get_all(skip=skip, limit=limit)
    return [PersonResponse.model_validate(p) for p in people]


@router.post(
    "",
    response_model=PersonDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_person(
    data: PersonCreate,
    db: AsyncSession = Depends(get_db),
) -> PersonDetailResponse:
    # Agent names must be unique
    if data.is_agent:
        existing = await db.execute(
            select(Person).where(Person.naam == data.naam, Person.is_agent == True)  # noqa: E712
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Er bestaat al een agent met de naam '{data.naam}'",
            )
    repo = PersonRepository(db)
    person = await repo.create(data)
    return PersonDetailResponse.model_validate(person)


@router.get("/search", response_model=list[PersonResponse])
async def search_people(
    q: str = Query("", min_length=0),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> list[PersonResponse]:
    repo = PersonRepository(db)
    if not q.strip():
        people = await repo.get_all(limit=limit)
    else:
        people = await repo.search(q.strip(), limit=limit)
    return [PersonResponse.model_validate(p) for p in people]


@router.get("/{id}/summary", response_model=PersonSummaryResponse)
async def get_person_summary(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PersonSummaryResponse:
    """Compact summary: task counts, top open tasks, and stakeholder nodes."""
    repo = PersonRepository(db)
    require_found(await repo.get(id), "Person")

    # Task counts
    open_count_stmt = (
        select(func.count())
        .select_from(Task)
        .where(Task.assignee_id == id, Task.status.in_(["open", "in_progress"]))
    )
    done_count_stmt = (
        select(func.count())
        .select_from(Task)
        .where(Task.assignee_id == id, Task.status == "done")
    )
    open_count = (await db.execute(open_count_stmt)).scalar() or 0
    done_count = (await db.execute(done_count_stmt)).scalar() or 0

    # Top open tasks (max 5, ordered by priority then deadline)
    open_tasks_stmt = (
        select(Task)
        .where(Task.assignee_id == id, Task.status.in_(["open", "in_progress"]))
        .order_by(
            # kritiek=0, hoog=1, normaal=2, laag=3
            func.array_position(["kritiek", "hoog", "normaal", "laag"], Task.priority),
            Task.deadline.asc().nullslast(),
        )
        .limit(5)
    )
    open_tasks_result = await db.execute(open_tasks_stmt)
    open_tasks = [
        PersonTaskSummary.model_validate(t) for t in open_tasks_result.scalars().all()
    ]

    # Stakeholder nodes
    stakeholder_stmt = (
        select(NodeStakeholder)
        .where(NodeStakeholder.person_id == id)
        .options(selectinload(NodeStakeholder.node))
    )
    stakeholder_result = await db.execute(stakeholder_stmt)
    stakeholder_nodes = [
        PersonStakeholderNode(
            node_id=s.node.id,
            node_title=s.node.title,
            node_type=s.node.node_type,
            stakeholder_rol=s.rol,
        )
        for s in stakeholder_result.scalars().all()
        if s.node is not None
    ]

    return PersonSummaryResponse(
        open_task_count=open_count,
        done_task_count=done_count,
        open_tasks=open_tasks,
        stakeholder_nodes=stakeholder_nodes,
    )


@router.get("/{id}", response_model=PersonDetailResponse)
async def get_person(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PersonDetailResponse:
    repo = PersonRepository(db)
    person = require_found(await repo.get(id), "Person")
    return PersonDetailResponse.model_validate(person)


@router.put("/{id}", response_model=PersonDetailResponse)
async def update_person(
    id: UUID,
    data: PersonUpdate,
    db: AsyncSession = Depends(get_db),
) -> PersonDetailResponse:
    repo = PersonRepository(db)
    person = require_found(await repo.update(id, data), "Person")
    return PersonDetailResponse.model_validate(person)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_person(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = PersonRepository(db)
    require_deleted(await repo.delete(id), "Person")


# --- Org placements ---


@router.get("/{id}/organisaties", response_model=list[PersonOrganisatieResponse])
async def list_person_organisaties(
    id: UUID,
    actief: bool = Query(True),
    db: AsyncSession = Depends(get_db),
) -> list[PersonOrganisatieResponse]:
    require_found(await db.get(Person, id), "Person")

    stmt = (
        select(PersonOrganisatieEenheid, OrganisatieEenheid.naam)
        .join(OrganisatieEenheid)
        .where(PersonOrganisatieEenheid.person_id == id)
    )
    if actief:
        stmt = stmt.where(PersonOrganisatieEenheid.eind_datum.is_(None))
    stmt = stmt.order_by(PersonOrganisatieEenheid.start_datum.desc())
    result = await db.execute(stmt)
    return [
        PersonOrganisatieResponse(
            id=row.PersonOrganisatieEenheid.id,
            person_id=row.PersonOrganisatieEenheid.person_id,
            organisatie_eenheid_id=row.PersonOrganisatieEenheid.organisatie_eenheid_id,
            organisatie_eenheid_naam=row.naam,
            dienstverband=row.PersonOrganisatieEenheid.dienstverband,
            start_datum=row.PersonOrganisatieEenheid.start_datum,
            eind_datum=row.PersonOrganisatieEenheid.eind_datum,
        )
        for row in result.all()
    ]


@router.post(
    "/{id}/organisaties",
    response_model=PersonOrganisatieResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_person_organisatie(
    id: UUID,
    data: PersonOrganisatieCreate,
    db: AsyncSession = Depends(get_db),
) -> PersonOrganisatieResponse:
    require_found(await db.get(Person, id), "Person")

    eenheid = require_found(
        await db.get(OrganisatieEenheid, data.organisatie_eenheid_id),
        "Organisatie-eenheid",
    )

    # Check for existing active placement in same org unit
    existing = await db.execute(
        select(PersonOrganisatieEenheid).where(
            PersonOrganisatieEenheid.person_id == id,
            PersonOrganisatieEenheid.organisatie_eenheid_id
            == data.organisatie_eenheid_id,
            PersonOrganisatieEenheid.eind_datum.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail="Persoon heeft al een actieve plaatsing bij deze eenheid",
        )

    placement = PersonOrganisatieEenheid(
        person_id=id,
        organisatie_eenheid_id=data.organisatie_eenheid_id,
        dienstverband=data.dienstverband,
        start_datum=data.start_datum,
    )
    db.add(placement)
    await db.flush()
    await db.refresh(placement)

    return PersonOrganisatieResponse(
        id=placement.id,
        person_id=placement.person_id,
        organisatie_eenheid_id=placement.organisatie_eenheid_id,
        organisatie_eenheid_naam=eenheid.naam,
        dienstverband=placement.dienstverband,
        start_datum=placement.start_datum,
        eind_datum=placement.eind_datum,
    )


@router.put(
    "/{id}/organisaties/{placement_id}",
    response_model=PersonOrganisatieResponse,
)
async def update_person_organisatie(
    id: UUID,
    placement_id: UUID,
    data: PersonOrganisatieUpdate,
    db: AsyncSession = Depends(get_db),
) -> PersonOrganisatieResponse:
    stmt = select(PersonOrganisatieEenheid).where(
        PersonOrganisatieEenheid.id == placement_id,
        PersonOrganisatieEenheid.person_id == id,
    )
    result = await db.execute(stmt)
    placement = require_found(result.scalar_one_or_none(), "Placement")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(placement, key, value)
    await db.flush()
    await db.refresh(placement)

    eenheid = await db.get(OrganisatieEenheid, placement.organisatie_eenheid_id)
    return PersonOrganisatieResponse(
        id=placement.id,
        person_id=placement.person_id,
        organisatie_eenheid_id=placement.organisatie_eenheid_id,
        organisatie_eenheid_naam=eenheid.naam if eenheid else "",
        dienstverband=placement.dienstverband,
        start_datum=placement.start_datum,
        eind_datum=placement.eind_datum,
    )


@router.delete(
    "/{id}/organisaties/{placement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_person_organisatie(
    id: UUID,
    placement_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    stmt = select(PersonOrganisatieEenheid).where(
        PersonOrganisatieEenheid.id == placement_id,
        PersonOrganisatieEenheid.person_id == id,
    )
    result = await db.execute(stmt)
    placement = require_found(result.scalar_one_or_none(), "Placement")
    await db.delete(placement)
    await db.flush()
