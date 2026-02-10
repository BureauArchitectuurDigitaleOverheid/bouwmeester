"""API routes for tasks."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_deleted, require_found
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.models.person import Person
from bouwmeester.repositories.task import TaskRepository
from bouwmeester.schema.inbox import InboxResponse
from bouwmeester.schema.task import (
    EenheidOverviewResponse,
    TaskCreate,
    TaskResponse,
    TaskStatus,
    TaskUpdate,
)
from bouwmeester.services.activity_service import ActivityService, resolve_actor
from bouwmeester.services.eenheid_overview_service import EenheidOverviewService
from bouwmeester.services.inbox_service import InboxService
from bouwmeester.services.mention_helper import sync_and_notify_mentions
from bouwmeester.services.notification_service import NotificationService

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    current_user: OptionalUser,
    status_filter: TaskStatus | None = Query(None, alias="status"),
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
        )
    return [TaskResponse.model_validate(t) for t in tasks]


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    data: TaskCreate,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    repo = TaskRepository(db)
    task = await repo.create(data)

    await sync_and_notify_mentions(
        db,
        "task",
        task.id,
        data.description,
        task.title,
        sender_id=data.assignee_id,
        source_task_id=task.id,
        source_node_id=task.node_id,
    )

    resolved_id, resolved_naam = await resolve_actor(current_user, actor_id, db)

    # Notify assignee
    notif_svc = NotificationService(db)
    if task.assignee_id:
        assignee = await db.get(Person, task.assignee_id)
        if assignee:
            await notif_svc.notify_task_assigned(
                task, assignee, actor_id=resolved_id
            )

    # Notify team manager
    if task.organisatie_eenheid_id:
        await notif_svc.notify_team_manager(
            task, task.organisatie_eenheid_id, exclude_person_id=task.assignee_id
        )

    await ActivityService(db).log_event(
        "task.created",
        actor_id=resolved_id,
        actor_naam=resolved_naam,
        task_id=task.id,
        node_id=task.node_id,
        details={
            "title": task.title,
            "assignee_id": str(task.assignee_id) if task.assignee_id else None,
        },
    )

    return TaskResponse.model_validate(task)


@router.get("/my", response_model=list[TaskResponse])
async def get_my_tasks(
    current_user: OptionalUser,
    person_id: UUID | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[TaskResponse]:
    # Use authenticated user's id when available, fall back to query param for dev
    effective_id = current_user.id if current_user is not None else person_id
    if effective_id is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="person_id is required")
    repo = TaskRepository(db)
    tasks = await repo.get_by_assignee(effective_id, skip=skip, limit=limit)
    return [TaskResponse.model_validate(t) for t in tasks]


@router.get("/inbox", response_model=InboxResponse)
async def get_task_inbox(
    current_user: OptionalUser,
    person_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
) -> InboxResponse:
    service = InboxService(db)
    return await service.get_inbox(person_id)


@router.get("/unassigned", response_model=list[TaskResponse])
async def get_unassigned_tasks(
    current_user: OptionalUser,
    organisatie_eenheid_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[TaskResponse]:
    repo = TaskRepository(db)
    tasks = await repo.get_unassigned(organisatie_eenheid_id)
    return [TaskResponse.model_validate(t) for t in tasks]


@router.get("/eenheid-overview", response_model=EenheidOverviewResponse)
async def get_eenheid_overview(
    current_user: OptionalUser,
    organisatie_eenheid_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
) -> EenheidOverviewResponse:
    """Overview of tasks for an organisatie-eenheid."""
    service = EenheidOverviewService(db)
    return await service.get_overview(organisatie_eenheid_id)


@router.get("/{id}", response_model=TaskResponse)
async def get_task(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    repo = TaskRepository(db)
    task = require_found(await repo.get(id), "Task")
    return TaskResponse.model_validate(task)


@router.get("/{id}/subtasks", response_model=list[TaskResponse])
async def get_task_subtasks(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> list[TaskResponse]:
    repo = TaskRepository(db)
    subtasks = await repo.get_subtasks(id)
    return [TaskResponse.model_validate(t) for t in subtasks]


@router.put("/{id}", response_model=TaskResponse)
async def update_task(
    id: UUID,
    data: TaskUpdate,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    repo = TaskRepository(db)

    # Capture old state before update
    old_task = await repo.get(id)
    old_assignee_id = old_task.assignee_id if old_task else None
    old_status = old_task.status if old_task else None
    old_org_unit_id = old_task.organisatie_eenheid_id if old_task else None

    task = require_found(await repo.update(id, data), "Task")

    await sync_and_notify_mentions(
        db,
        "task",
        task.id,
        data.description,
        task.title,
        sender_id=data.assignee_id,
        source_task_id=task.id,
        source_node_id=task.node_id,
    )

    resolved_id, resolved_naam = await resolve_actor(current_user, actor_id, db)
    notif_svc = NotificationService(db)

    # Detect assignee changes
    new_assignee_id = task.assignee_id
    if new_assignee_id and new_assignee_id != old_assignee_id:
        new_assignee = await db.get(Person, new_assignee_id)
        if new_assignee:
            if old_assignee_id:
                # Reassignment: notify both
                await notif_svc.notify_task_reassigned(
                    task, old_assignee_id, new_assignee
                )
            else:
                # First assignment
                await notif_svc.notify_task_assigned(
                    task,
                    new_assignee,
                    actor_id=resolved_id,
                )

    # Detect status → done
    if task.status == "done" and old_status != "done":
        await notif_svc.notify_task_completed(task, actor_id=resolved_id)

    # Detect org unit change
    new_org_unit_id = task.organisatie_eenheid_id
    if new_org_unit_id and new_org_unit_id != old_org_unit_id:
        await notif_svc.notify_team_manager(
            task, new_org_unit_id, exclude_person_id=task.assignee_id
        )

    await ActivityService(db).log_event(
        "task.updated",
        actor_id=resolved_id,
        actor_naam=resolved_naam,
        task_id=task.id,
        node_id=task.node_id,
        details={"title": task.title},
    )

    return TaskResponse.model_validate(task)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    id: UUID,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = TaskRepository(db)
    task = await repo.get(id)
    task_title = task.title if task else None
    task_node_id = task.node_id if task else None
    require_deleted(await repo.delete(id), "Task")
    resolved_id, resolved_naam = await resolve_actor(current_user, actor_id, db)
    await ActivityService(db).log_event(
        "task.deleted",
        actor_id=resolved_id,
        actor_naam=resolved_naam,
        details={
            "task_id": str(id),
            "node_id": str(task_node_id) if task_node_id else None,
            "title": task_title,
        },
    )
