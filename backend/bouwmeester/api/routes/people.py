"""API routes for people."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.api.deps import require_deleted, require_found
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.models.node_stakeholder import NodeStakeholder
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_email import PersonEmail
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.person_phone import PersonPhone
from bouwmeester.models.task import Task
from bouwmeester.repositories.person import PersonRepository
from bouwmeester.schema.person import (
    PHONE_LABELS,
    PersonCreate,
    PersonDetailResponse,
    PersonEmailCreate,
    PersonEmailResponse,
    PersonOrganisatieCreate,
    PersonOrganisatieResponse,
    PersonOrganisatieUpdate,
    PersonPhoneCreate,
    PersonPhoneResponse,
    PersonResponse,
    PersonStakeholderNode,
    PersonSummaryResponse,
    PersonTaskSummary,
    PersonUpdate,
)
from bouwmeester.services.activity_service import log_activity

router = APIRouter(prefix="/people", tags=["people"])


@router.get("", response_model=list[PersonResponse])
async def list_people(
    current_user: OptionalUser,
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
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
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

    # Also create a PersonEmail row if email was provided
    if data.email:
        email_obj = PersonEmail(person_id=person.id, email=data.email, is_default=True)
        db.add(email_obj)
        await db.flush()
        await db.refresh(person, attribute_names=["emails"])

    await log_activity(
        db,
        current_user,
        actor_id,
        "person.created",
        details={"person_id": str(person.id), "naam": person.naam},
    )

    # Re-fetch with eager loading for response
    person = await repo.get(person.id)
    return PersonDetailResponse.model_validate(person)


@router.get("/search", response_model=list[PersonResponse])
async def search_people(
    current_user: OptionalUser,
    q: str = Query("", min_length=0, max_length=500),
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
    current_user: OptionalUser,
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
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> PersonDetailResponse:
    repo = PersonRepository(db)
    person = require_found(await repo.get(id), "Person")
    return PersonDetailResponse.model_validate(person)


@router.put("/{id}", response_model=PersonDetailResponse)
async def update_person(
    id: UUID,
    data: PersonUpdate,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> PersonDetailResponse:
    repo = PersonRepository(db)
    require_found(await repo.update(id, data), "Person")

    # Re-fetch with eager loading for response
    person = require_found(await repo.get(id), "Person")

    await log_activity(
        db,
        current_user,
        actor_id,
        "person.updated",
        details={"person_id": str(person.id), "naam": person.naam},
    )

    return PersonDetailResponse.model_validate(person)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_person(
    id: UUID,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = PersonRepository(db)
    person = await repo.get(id)
    person_naam = person.naam if person else None
    require_deleted(await repo.delete(id), "Person")
    await log_activity(
        db,
        current_user,
        actor_id,
        "person.deleted",
        details={"person_id": str(id), "naam": person_naam},
    )


# --- Org placements ---


@router.get("/{id}/organisaties", response_model=list[PersonOrganisatieResponse])
async def list_person_organisaties(
    id: UUID,
    current_user: OptionalUser,
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
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
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

    await log_activity(
        db,
        current_user,
        actor_id,
        "person.organisatie_added",
        details={
            "person_id": str(id),
            "organisatie_eenheid_id": str(data.organisatie_eenheid_id),
            "organisatie_eenheid_naam": eenheid.naam,
            "dienstverband": data.dienstverband,
        },
    )

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
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
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

    await log_activity(
        db,
        current_user,
        actor_id,
        "person.organisatie_updated",
        details={
            "person_id": str(id),
            "placement_id": str(placement_id),
            "organisatie_eenheid_naam": eenheid.naam if eenheid else None,
        },
    )
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
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
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

    await log_activity(
        db,
        current_user,
        actor_id,
        "person.organisatie_removed",
        details={"person_id": str(id), "placement_id": str(placement_id)},
    )


# --- Emails ---


@router.post(
    "/{id}/emails",
    response_model=PersonEmailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_person_email(
    id: UUID,
    data: PersonEmailCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> PersonEmailResponse:
    require_found(await db.get(Person, id), "Person")
    email = data.email.strip().lower()

    # Check uniqueness
    existing = await db.execute(
        select(PersonEmail).where(PersonEmail.email == email)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail=f"E-mailadres '{email}' is al in gebruik",
        )

    # If this is the first email, auto-set as default
    count_result = await db.execute(
        select(func.count()).select_from(PersonEmail).where(PersonEmail.person_id == id)
    )
    is_first = (count_result.scalar() or 0) == 0

    email_obj = PersonEmail(
        person_id=id,
        email=email,
        is_default=data.is_default or is_first,
    )
    db.add(email_obj)

    # If setting as default, unset others
    if email_obj.is_default:
        for existing_email in (
            await db.execute(
                select(PersonEmail).where(
                    PersonEmail.person_id == id,
                    PersonEmail.email != email,
                )
            )
        ).scalars():
            existing_email.is_default = False

    await db.flush()
    await db.refresh(email_obj)
    return PersonEmailResponse.model_validate(email_obj)


@router.delete(
    "/{id}/emails/{email_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_person_email(
    id: UUID,
    email_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    stmt = select(PersonEmail).where(
        PersonEmail.id == email_id,
        PersonEmail.person_id == id,
    )
    result = await db.execute(stmt)
    email_obj = require_found(result.scalar_one_or_none(), "Email")
    was_default = email_obj.is_default
    await db.delete(email_obj)
    await db.flush()

    # Auto-promote another email to default if we deleted the default
    if was_default:
        next_email = (
            await db.execute(
                select(PersonEmail)
                .where(PersonEmail.person_id == id)
                .order_by(PersonEmail.created_at.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if next_email:
            next_email.is_default = True
            await db.flush()


@router.post(
    "/{id}/emails/{email_id}/set-default",
    response_model=PersonEmailResponse,
)
async def set_default_email(
    id: UUID,
    email_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> PersonEmailResponse:
    # Unset all defaults for this person
    all_emails = (
        (await db.execute(select(PersonEmail).where(PersonEmail.person_id == id)))
        .scalars()
        .all()
    )
    target = None
    for e in all_emails:
        if e.id == email_id:
            e.is_default = True
            target = e
        else:
            e.is_default = False

    if target is None:
        raise HTTPException(status_code=404, detail="Email niet gevonden")

    await db.flush()
    await db.refresh(target)
    return PersonEmailResponse.model_validate(target)


# --- Phones ---


@router.post(
    "/{id}/phones",
    response_model=PersonPhoneResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_person_phone(
    id: UUID,
    data: PersonPhoneCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> PersonPhoneResponse:
    require_found(await db.get(Person, id), "Person")

    if data.label not in PHONE_LABELS:
        raise HTTPException(
            status_code=422,
            detail=f"Label moet een van {list(PHONE_LABELS.keys())} zijn",
        )

    # If this is the first phone, auto-set as default
    count_result = await db.execute(
        select(func.count()).select_from(PersonPhone).where(PersonPhone.person_id == id)
    )
    is_first = (count_result.scalar() or 0) == 0

    phone_obj = PersonPhone(
        person_id=id,
        phone_number=data.phone_number,
        label=data.label,
        is_default=data.is_default or is_first,
    )
    db.add(phone_obj)

    # If setting as default, unset others
    if phone_obj.is_default:
        for existing_phone in (
            await db.execute(
                select(PersonPhone).where(
                    PersonPhone.person_id == id,
                )
            )
        ).scalars():
            if existing_phone is not phone_obj:
                existing_phone.is_default = False

    await db.flush()
    await db.refresh(phone_obj)
    return PersonPhoneResponse.model_validate(phone_obj)


@router.delete(
    "/{id}/phones/{phone_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_person_phone(
    id: UUID,
    phone_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    stmt = select(PersonPhone).where(
        PersonPhone.id == phone_id,
        PersonPhone.person_id == id,
    )
    result = await db.execute(stmt)
    phone_obj = require_found(result.scalar_one_or_none(), "Telefoon")
    was_default = phone_obj.is_default
    await db.delete(phone_obj)
    await db.flush()

    # Auto-promote another phone to default if we deleted the default
    if was_default:
        next_phone = (
            await db.execute(
                select(PersonPhone)
                .where(PersonPhone.person_id == id)
                .order_by(PersonPhone.created_at.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if next_phone:
            next_phone.is_default = True
            await db.flush()


@router.post(
    "/{id}/phones/{phone_id}/set-default",
    response_model=PersonPhoneResponse,
)
async def set_default_phone(
    id: UUID,
    phone_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> PersonPhoneResponse:
    all_phones = (
        (await db.execute(select(PersonPhone).where(PersonPhone.person_id == id)))
        .scalars()
        .all()
    )
    target = None
    for p in all_phones:
        if p.id == phone_id:
            p.is_default = True
            target = p
        else:
            p.is_default = False

    if target is None:
        raise HTTPException(status_code=404, detail="Telefoonnummer niet gevonden")

    await db.flush()
    await db.refresh(target)
    return PersonPhoneResponse.model_validate(target)
