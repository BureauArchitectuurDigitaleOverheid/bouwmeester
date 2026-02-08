"""API routes for tasks."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_found
from bouwmeester.core.database import get_db
from bouwmeester.repositories.task import TaskRepository
from bouwmeester.schema.inbox import InboxResponse
from bouwmeester.schema.task import (
    EenheidOverviewResponse,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
)
from bouwmeester.services.eenheid_overview_service import EenheidOverviewService
from bouwmeester.services.inbox_service import InboxService
from bouwmeester.services.mention_helper import sync_and_notify_mentions

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
        )
    return [TaskResponse.model_validate(t) for t in tasks]


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    data: TaskCreate,
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    repo = TaskRepository(db)
    task = await repo.create(data)

    await sync_and_notify_mentions(
        db, "task", task.id, data.description, task.title,
        sender_id=data.assignee_id,
        source_task_id=task.id,
        source_node_id=task.node_id,
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
    service = EenheidOverviewService(db)
    return await service.get_overview(organisatie_eenheid_id)


@router.get("/{id}", response_model=TaskResponse)
async def get_task(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    repo = TaskRepository(db)
    task = require_found(await repo.get(id), "Task")
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
    task = require_found(await repo.update(id, data), "Task")

    await sync_and_notify_mentions(
        db, "task", task.id, data.description, task.title,
        sender_id=data.assignee_id,
        source_task_id=task.id,
        source_node_id=task.node_id,
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
