"""API routes for tasks."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import get_db
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.task import Task
from bouwmeester.repositories.task import TaskRepository
from bouwmeester.schema.inbox import InboxResponse
from bouwmeester.schema.task import (
    EenheidOverviewResponse,
    EenheidPersonTaskStats,
    EenheidSubeenheidStats,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
)
from bouwmeester.services.inbox_service import InboxService
from bouwmeester.services.mention_service import MentionService
from bouwmeester.services.notification_service import NotificationService

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    status_filter: str | None = Query(None, alias="status"),
    node_id: UUID | None = Query(None),
    assignee_id: UUID | None = Query(None),
    organisatie_eenheid_id: UUID | None = Query(None),
    include_children: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[TaskResponse]:
    repo = TaskRepository(db)
    if node_id is not None:
        tasks = await repo.get_by_node(node_id, skip=skip, limit=limit)
    elif assignee_id is not None:
        tasks = await repo.get_by_assignee(assignee_id, skip=skip, limit=limit)
    elif organisatie_eenheid_id is not None:
        tasks = await repo.get_by_organisatie_eenheid(
            organisatie_eenheid_id,
            include_children=include_children,
            skip=skip,
            limit=limit,
        )
    else:
        tasks = await repo.get_all(
            skip=skip,
            limit=limit,
            status=status_filter,
            organisatie_eenheid_id=organisatie_eenheid_id,
            include_children=include_children,
        )
    return [TaskResponse.model_validate(t) for t in tasks]


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    data: TaskCreate,
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    repo = TaskRepository(db)
    task = await repo.create(data)

    # Sync mentions from description
    if data.description:
        mention_svc = MentionService(db)
        new_mentions = await mention_svc.sync_mentions(
            "task", task.id, data.description, data.assignee_id
        )
        # Notify @mentioned persons
        notif_svc = NotificationService(db)
        for m in new_mentions:
            if m.mention_type == "person":
                await notif_svc.notify_mention(
                    m.target_id,
                    "task",
                    task.title,
                    source_task_id=task.id,
                    source_node_id=task.node_id,
                    sender_id=data.assignee_id,
                )

    return TaskResponse.model_validate(task)


@router.get("/my", response_model=list[TaskResponse])
async def get_my_tasks(
    person_id: UUID = Query(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[TaskResponse]:
    repo = TaskRepository(db)
    tasks = await repo.get_by_assignee(person_id, skip=skip, limit=limit)
    return [TaskResponse.model_validate(t) for t in tasks]


@router.get("/inbox", response_model=InboxResponse)
async def get_task_inbox(
    person_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
) -> InboxResponse:
    service = InboxService(db)
    return await service.get_inbox(person_id)


@router.get("/unassigned", response_model=list[TaskResponse])
async def get_unassigned_tasks(
    organisatie_eenheid_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[TaskResponse]:
    repo = TaskRepository(db)
    tasks = await repo.get_unassigned(organisatie_eenheid_id)
    return [TaskResponse.model_validate(t) for t in tasks]


@router.get("/eenheid-overview", response_model=EenheidOverviewResponse)
async def get_eenheid_overview(
    organisatie_eenheid_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
) -> EenheidOverviewResponse:
    """Overview of tasks for an organisatie-eenheid."""
    # Get descendant unit IDs
    cte = (
        select(OrganisatieEenheid.id)
        .where(OrganisatieEenheid.id == organisatie_eenheid_id)
        .cte(name="descendants", recursive=True)
    )
    cte = cte.union_all(
        select(OrganisatieEenheid.id).where(OrganisatieEenheid.parent_id == cte.c.id)
    )
    desc_ids_stmt = select(cte.c.id)
    desc_result = await db.execute(desc_ids_stmt)
    all_unit_ids = list(desc_result.scalars().all())

    # Unassigned count
    unassigned_stmt = (
        select(func.count())
        .select_from(Task)
        .where(
            Task.organisatie_eenheid_id.in_(all_unit_ids),
            Task.assignee_id.is_(None),
            Task.status.notin_(["done", "cancelled"]),
        )
    )
    unassigned_result = await db.execute(unassigned_stmt)
    unassigned_count = unassigned_result.scalar_one()

    # Per-person stats: people in this unit (via junction table)
    people_stmt = (
        select(Person)
        .join(
            PersonOrganisatieEenheid,
            PersonOrganisatieEenheid.person_id == Person.id,
        )
        .where(
            PersonOrganisatieEenheid.organisatie_eenheid_id == organisatie_eenheid_id,
            PersonOrganisatieEenheid.eind_datum.is_(None),
        )
        .order_by(Person.naam)
    )
    people_result = await db.execute(people_stmt)
    people = list(people_result.scalars().all())

    by_person: list[EenheidPersonTaskStats] = []
    today = date.today()
    for person in people:
        tasks_stmt = (
            select(Task.status, Task.deadline, func.count())
            .where(Task.assignee_id == person.id)
            .group_by(Task.status, Task.deadline)
        )
        tasks_result = await db.execute(tasks_stmt)
        rows = tasks_result.all()

        open_count = 0
        in_progress_count = 0
        done_count = 0
        overdue_count = 0
        for task_status, deadline, cnt in rows:
            if task_status == "open":
                open_count += cnt
            elif task_status == "in_progress":
                in_progress_count += cnt
            elif task_status == "done":
                done_count += cnt
            if (
                task_status in ("open", "in_progress")
                and deadline is not None
                and deadline < today
            ):
                overdue_count += cnt

        by_person.append(
            EenheidPersonTaskStats(
                person_id=person.id,
                person_naam=person.naam,
                open_count=open_count,
                in_progress_count=in_progress_count,
                done_count=done_count,
                overdue_count=overdue_count,
            )
        )

    # Per-subeenheid stats: direct child units
    children_stmt = (
        select(OrganisatieEenheid)
        .where(OrganisatieEenheid.parent_id == organisatie_eenheid_id)
        .order_by(OrganisatieEenheid.naam)
    )
    children_result = await db.execute(children_stmt)
    children = list(children_result.scalars().all())

    by_subeenheid: list[EenheidSubeenheidStats] = []
    for child in children:
        # Get all descendant IDs for this child
        child_cte = (
            select(OrganisatieEenheid.id)
            .where(OrganisatieEenheid.id == child.id)
            .cte(name=f"child_desc_{child.id.hex[:8]}", recursive=True)
        )
        child_cte = child_cte.union_all(
            select(OrganisatieEenheid.id).where(
                OrganisatieEenheid.parent_id == child_cte.c.id
            )
        )
        child_ids_stmt = select(child_cte.c.id)
        child_ids_result = await db.execute(child_ids_stmt)
        child_unit_ids = list(child_ids_result.scalars().all())

        stats_stmt = (
            select(Task.status, func.count())
            .where(Task.organisatie_eenheid_id.in_(child_unit_ids))
            .group_by(Task.status)
        )
        stats_result = await db.execute(stats_stmt)
        stats_rows = stats_result.all()

        open_c = sum(c for s, c in stats_rows if s == "open")
        ip_c = sum(c for s, c in stats_rows if s == "in_progress")
        done_c = sum(c for s, c in stats_rows if s == "done")

        by_subeenheid.append(
            EenheidSubeenheidStats(
                eenheid_id=child.id,
                eenheid_naam=child.naam,
                eenheid_type=child.type,
                open_count=open_c,
                in_progress_count=ip_c,
                done_count=done_c,
            )
        )

    return EenheidOverviewResponse(
        unassigned_count=unassigned_count,
        by_person=by_person,
        by_subeenheid=by_subeenheid,
    )


@router.get("/{id}", response_model=TaskResponse)
async def get_task(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    repo = TaskRepository(db)
    task = await repo.get(id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse.model_validate(task)


@router.get("/{id}/subtasks", response_model=list[TaskResponse])
async def get_task_subtasks(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[TaskResponse]:
    repo = TaskRepository(db)
    subtasks = await repo.get_subtasks(id)
    return [TaskResponse.model_validate(t) for t in subtasks]


@router.put("/{id}", response_model=TaskResponse)
async def update_task(
    id: UUID,
    data: TaskUpdate,
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    repo = TaskRepository(db)
    task = await repo.update(id, data)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # Sync mentions from description
    if data.description is not None:
        mention_svc = MentionService(db)
        new_mentions = await mention_svc.sync_mentions(
            "task", task.id, data.description, data.assignee_id
        )
        notif_svc = NotificationService(db)
        for m in new_mentions:
            if m.mention_type == "person":
                await notif_svc.notify_mention(
                    m.target_id,
                    "task",
                    task.title,
                    source_task_id=task.id,
                    source_node_id=task.node_id,
                    sender_id=data.assignee_id,
                )

    return TaskResponse.model_validate(task)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = TaskRepository(db)
    deleted = await repo.delete(id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
