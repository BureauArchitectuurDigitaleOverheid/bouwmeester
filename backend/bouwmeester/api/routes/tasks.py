"""API routes for tasks."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import get_db
from bouwmeester.repositories.task import TaskRepository
from bouwmeester.schema.inbox import InboxResponse
from bouwmeester.schema.task import TaskCreate, TaskResponse, TaskUpdate
from bouwmeester.services.inbox_service import InboxService

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    status_filter: str | None = Query(None, alias="status"),
    node_id: UUID | None = Query(None),
    assignee_id: UUID | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[TaskResponse]:
    repo = TaskRepository(db)
    if node_id is not None:
        tasks = await repo.get_by_node(node_id, skip=skip, limit=limit)
    elif assignee_id is not None:
        tasks = await repo.get_by_assignee(assignee_id, skip=skip, limit=limit)
    else:
        tasks = await repo.get_all(skip=skip, limit=limit, status=status_filter)
    return [TaskResponse.model_validate(t) for t in tasks]


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    data: TaskCreate,
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    repo = TaskRepository(db)
    task = await repo.create(data)
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
