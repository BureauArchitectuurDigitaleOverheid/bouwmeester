"""API routes for people."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.api.deps import require_deleted, require_found
from bouwmeester.core.api_key import generate_api_key, hash_api_key
from bouwmeester.core.auth import AdminUser, OptionalUser
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
    ApiKeyResponse,
    PersonCreate,
    PersonCreateResponse,
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
    """List all people (users and agents)."""
    repo = PersonRepository(db)
    people = await repo.get_all(skip=skip, limit=limit)
    result = []
    for p in people:
        resp = PersonResponse.model_validate(p)
        resp.has_api_key = p.api_key_hash is not None
        result.append(resp)
    return result


@router.post(
    "",
    response_model=PersonCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_person(
    data: PersonCreate,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> PersonCreateResponse:
    """Create a person.

    Agents (is_agent=true) get an auto-generated API key (admin only).
    """
    # Agent creation requires admin privileges (agents bypass email whitelist).
    # In dev mode (no OIDC) current_user is None so all access is open.
    if data.is_agent and current_user is not None and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Alleen administrators kunnen agents aanmaken",
        )

    # Agent names must be unique among active agents
    if data.is_agent:
        existing = await db.execute(
            select(Person).where(
                Person.naam == data.naam,
                Person.is_agent == True,  # noqa: E712
                Person.is_active == True,  # noqa: E712
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Er bestaat al een agent met de naam '{data.naam}'",
            )
    repo = PersonRepository(db)
    person = await repo.create(data)

    # Auto-generate API key for agents.
    plaintext_key: str | None = None
    if data.is_agent:
        plaintext_key = generate_api_key()
        person.api_key_hash = hash_api_key(plaintext_key)
        await db.flush()

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
    resp = PersonCreateResponse.model_validate(person)
    # Return plaintext key one-time on creation.
    if plaintext_key:
        resp.api_key = plaintext_key
        resp.has_api_key = True
    return resp


@router.get("/search", response_model=list[PersonResponse])
async def search_people(
    current_user: OptionalUser,
    q: str = Query("", min_length=0, max_length=500),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> list[PersonResponse]:
    """Search people by name. Returns all people if query is empty."""
    repo = PersonRepository(db)
    if not q.strip():
        people = await repo.get_all(limit=limit)
    else:
        people = await repo.search(q.strip(), limit=limit)
    result = []
    for p in people:
        resp = PersonResponse.model_validate(p)
        resp.has_api_key = p.api_key_hash is not None
        result.append(resp)
    return result


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
    """Get detailed person info including emails, phones, and org placements."""
    repo = PersonRepository(db)
    person = require_found(await repo.get(id), "Person")
    resp = PersonDetailResponse.model_validate(person)
    resp.has_api_key = person.api_key_hash is not None
    return resp


@router.put("/{id}", response_model=PersonDetailResponse)
async def update_person(
    id: UUID,
    data: PersonUpdate,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> PersonDetailResponse:
    """Update person fields (naam, functie, etc.)."""
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

    resp = PersonDetailResponse.model_validate(person)
    resp.has_api_key = person.api_key_hash is not None
    return resp


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_person(
    id: UUID,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a person permanently."""
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


# --- API key management ---


@router.post("/{id}/rotate-api-key", response_model=ApiKeyResponse)
async def rotate_api_key(
    id: UUID,
    admin: AdminUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyResponse:
    """Generate a new API key, replacing the previous one.

    The plaintext key is returned once — it cannot be retrieved afterwards.
    """
    person = require_found(await db.get(Person, id), "Person")
    if not person.is_agent:
        raise HTTPException(
            status_code=400,
            detail="API keys zijn alleen beschikbaar voor agents",
        )

    plaintext_key = generate_api_key()
    person.api_key_hash = hash_api_key(plaintext_key)
    await db.flush()

    await log_activity(
        db,
        admin,
        actor_id,
        "person.api_key_rotated",
        details={"person_id": str(person.id), "naam": person.naam},
    )

    return ApiKeyResponse(api_key=plaintext_key, person_id=person.id)


# --- Org placements ---


@router.get("/{id}/organisaties", response_model=list[PersonOrganisatieResponse])
async def list_person_organisaties(
    id: UUID,
    current_user: OptionalUser,
    actief: bool = Query(True),
    db: AsyncSession = Depends(get_db),
) -> list[PersonOrganisatieResponse]:
    """List org unit placements for a person. Defaults to active placements only."""
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
    """Place a person in an org unit. Returns 409 if already active in that unit."""
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
    """Update an org placement (e.g. set eind_datum to end placement)."""
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
    """Delete an org placement permanently."""
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
    """Add an email address to a person. First email auto-becomes default."""
    require_found(await db.get(Person, id), "Person")
    email = data.email.strip().lower()

    # Check uniqueness
    existing = await db.execute(select(PersonEmail).where(PersonEmail.email == email))
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

    # If setting as default, unset others with a bulk update
    if email_obj.is_default:
        await db.flush()  # flush to get email_obj.id assigned
        await db.execute(
            update(PersonEmail)
            .where(
                PersonEmail.person_id == id,
                PersonEmail.id != email_obj.id,
            )
            .values(is_default=False)
        )

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
    """Remove an email address. Auto-promotes another email to default if needed."""
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
    """Set an email as the default for a person."""
    # Verify the target email exists and belongs to this person
    target = (
        await db.execute(
            select(PersonEmail).where(
                PersonEmail.id == email_id,
                PersonEmail.person_id == id,
            )
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Email niet gevonden")

    # Bulk unset all defaults, then set the target
    await db.execute(
        update(PersonEmail).where(PersonEmail.person_id == id).values(is_default=False)
    )
    await db.execute(
        update(PersonEmail)
        .where(PersonEmail.id == email_id, PersonEmail.person_id == id)
        .values(is_default=True)
    )

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
    """Add a phone number to a person. First phone auto-becomes default."""
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

    # If setting as default, unset others with a bulk update
    if phone_obj.is_default:
        await db.flush()  # flush to get phone_obj.id assigned
        await db.execute(
            update(PersonPhone)
            .where(
                PersonPhone.person_id == id,
                PersonPhone.id != phone_obj.id,
            )
            .values(is_default=False)
        )

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
    """Remove a phone number. Auto-promotes another to default if needed."""
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
    """Set a phone number as the default for a person."""
    # Verify the target phone exists and belongs to this person
    target = (
        await db.execute(
            select(PersonPhone).where(
                PersonPhone.id == phone_id,
                PersonPhone.person_id == id,
            )
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Telefoonnummer niet gevonden")

    # Bulk unset all defaults, then set the target
    await db.execute(
        update(PersonPhone).where(PersonPhone.person_id == id).values(is_default=False)
    )
    await db.execute(
        update(PersonPhone)
        .where(PersonPhone.id == phone_id, PersonPhone.person_id == id)
        .values(is_default=True)
    )

    await db.flush()
    await db.refresh(target)
    return PersonPhoneResponse.model_validate(target)
