"""Repository for Task CRUD and queries."""

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.models.task import Task
from bouwmeester.schema.task import TaskCreate, TaskUpdate


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id: UUID) -> Task | None:
        stmt = select(Task).where(Task.id == id).options(selectinload(Task.assignee))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        status: str | None = None,
    ) -> list[Task]:
        stmt = (
            select(Task).options(selectinload(Task.assignee)).offset(skip).limit(limit)
        )
        if status is not None:
            stmt = stmt.where(Task.status == status)
        stmt = stmt.order_by(Task.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: TaskCreate) -> Task:
        task = Task(**data.model_dump())
        self.session.add(task)
        await self.session.flush()
        await self.session.refresh(task, attribute_names=["assignee"])
        return task

    async def update(self, id: UUID, data: TaskUpdate) -> Task | None:
        task = await self.session.get(Task, id)
        if task is None:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(task, key, value)
        await self.session.flush()
        await self.session.refresh(task, attribute_names=["updated_at", "assignee"])
        return task

    async def delete(self, id: UUID) -> bool:
        task = await self.session.get(Task, id)
        if task is None:
            return False
        await self.session.delete(task)
        await self.session.flush()
        return True

    async def get_by_assignee(
        self,
        assignee_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Task]:
        stmt = (
            select(Task)
            .where(Task.assignee_id == assignee_id)
            .options(selectinload(Task.assignee))
            .offset(skip)
            .limit(limit)
            .order_by(Task.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_node(
        self,
        node_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Task]:
        stmt = (
            select(Task)
            .where(Task.node_id == node_id)
            .options(selectinload(Task.assignee))
            .offset(skip)
            .limit(limit)
            .order_by(Task.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_overdue(
        self,
        assignee_id: UUID | None = None,
    ) -> list[Task]:
        stmt = (
            select(Task)
            .where(
                Task.deadline < date.today(),
                Task.status.notin_(["done", "cancelled"]),
            )
            .options(selectinload(Task.assignee))
        )
        if assignee_id is not None:
            stmt = stmt.where(Task.assignee_id == assignee_id)
        stmt = stmt.order_by(Task.deadline.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
