"""Repository for Task CRUD and queries."""

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.task import Task
from bouwmeester.schema.task import TaskCreate, TaskUpdate


def _task_options():
    """Standard eager-load options for task queries."""
    return [
        selectinload(Task.assignee),
        selectinload(Task.organisatie_eenheid),
        selectinload(Task.subtasks).selectinload(Task.assignee),
    ]


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id: UUID) -> Task | None:
        stmt = select(Task).where(Task.id == id).options(*_task_options())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        status: str | None = None,
        organisatie_eenheid_id: UUID | None = None,
        include_children: bool = False,
    ) -> list[Task]:
        stmt = select(Task).options(*_task_options()).offset(skip).limit(limit)
        if status is not None:
            stmt = stmt.where(Task.status == status)
        if organisatie_eenheid_id is not None:
            if include_children:
                unit_ids = await self._get_descendant_ids(organisatie_eenheid_id)
                stmt = stmt.where(Task.organisatie_eenheid_id.in_(unit_ids))
            else:
                stmt = stmt.where(Task.organisatie_eenheid_id == organisatie_eenheid_id)
        stmt = stmt.order_by(Task.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: TaskCreate) -> Task:
        task = Task(**data.model_dump())
        self.session.add(task)
        await self.session.flush()
        await self.session.refresh(
            task,
            attribute_names=[
                "assignee",
                "organisatie_eenheid",
                "subtasks",
            ],
        )
        return task

    async def update(self, id: UUID, data: TaskUpdate) -> Task | None:
        task = await self.session.get(Task, id)
        if task is None:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(task, key, value)
        await self.session.flush()
        await self.session.refresh(
            task,
            attribute_names=[
                "updated_at",
                "assignee",
                "organisatie_eenheid",
                "subtasks",
            ],
        )
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
            .options(*_task_options())
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
            .options(*_task_options())
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
            .options(*_task_options())
        )
        if assignee_id is not None:
            stmt = stmt.where(Task.assignee_id == assignee_id)
        stmt = stmt.order_by(Task.deadline.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_organisatie_eenheid(
        self,
        eenheid_id: UUID,
        include_children: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Task]:
        if include_children:
            unit_ids = await self._get_descendant_ids(eenheid_id)
            stmt = select(Task).where(Task.organisatie_eenheid_id.in_(unit_ids))
        else:
            stmt = select(Task).where(Task.organisatie_eenheid_id == eenheid_id)
        stmt = (
            stmt.options(*_task_options())
            .offset(skip)
            .limit(limit)
            .order_by(Task.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_unassigned(
        self,
        organisatie_eenheid_id: UUID | None = None,
    ) -> list[Task]:
        stmt = (
            select(Task)
            .where(
                Task.assignee_id.is_(None),
                Task.status.notin_(["done", "cancelled"]),
            )
            .options(*_task_options())
        )
        if organisatie_eenheid_id is not None:
            stmt = stmt.where(Task.organisatie_eenheid_id == organisatie_eenheid_id)
        stmt = stmt.order_by(Task.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_subtasks(self, parent_id: UUID) -> list[Task]:
        stmt = (
            select(Task)
            .where(Task.parent_id == parent_id)
            .options(*_task_options())
            .order_by(Task.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _get_descendant_ids(self, root_id: UUID) -> list[UUID]:
        """Get all descendant unit IDs (including root) using a recursive CTE."""
        cte = (
            select(OrganisatieEenheid.id)
            .where(OrganisatieEenheid.id == root_id)
            .cte(name="descendants", recursive=True)
        )
        cte = cte.union_all(
            select(OrganisatieEenheid.id).where(
                OrganisatieEenheid.parent_id == cte.c.id
            )
        )
        stmt = select(cte.c.id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
