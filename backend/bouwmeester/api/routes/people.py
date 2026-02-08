"""API routes for people."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.core.database import get_db
from bouwmeester.models.node_stakeholder import NodeStakeholder
from bouwmeester.models.person import Person
from bouwmeester.models.task import Task
from bouwmeester.repositories.person import PersonRepository
from bouwmeester.schema.person import (
    PersonCreate,
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
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[PersonResponse]:
    repo = PersonRepository(db)
    people = await repo.get_all(skip=skip, limit=limit)
    return [PersonResponse.model_validate(p) for p in people]


@router.post("", response_model=PersonResponse, status_code=status.HTTP_201_CREATED)
async def create_person(
    data: PersonCreate,
    db: AsyncSession = Depends(get_db),
) -> PersonResponse:
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
    return PersonResponse.model_validate(person)


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
    person = await repo.get(id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")

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
            func.array_position(
                ["kritiek", "hoog", "normaal", "laag"], Task.priority
            ),
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


@router.get("/{id}", response_model=PersonResponse)
async def get_person(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PersonResponse:
    repo = PersonRepository(db)
    person = await repo.get(id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return PersonResponse.model_validate(person)


@router.put("/{id}", response_model=PersonResponse)
async def update_person(
    id: UUID,
    data: PersonUpdate,
    db: AsyncSession = Depends(get_db),
) -> PersonResponse:
    repo = PersonRepository(db)
    person = await repo.update(id, data)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return PersonResponse.model_validate(person)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_person(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = PersonRepository(db)
    deleted = await repo.delete(id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Person not found")
