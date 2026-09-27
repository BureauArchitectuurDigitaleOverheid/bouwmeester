"""Repository for Task CRUD and queries."""

from datetime import date
from uuid import UUID

from sqlalchemy import distinct, select
from sqlalchemy.orm import selectinload

from bouwmeester.core.org_context import OrgContext, apply_task_filter
from bouwmeester.models.task import Task
from bouwmeester.repositories.base import BaseRepository
from bouwmeester.schema.task import TaskCreate, TaskUpdate

REORDER_MISMATCH = "Geef precies de subtaken van deze taak op, elk één keer"


def task_options():
    """Standard eager-load options for task queries."""
    return [
        selectinload(Task.assignee),
        selectinload(Task.organisatie_eenheid),
        selectinload(Task.node),
        selectinload(Task.opdracht),
        selectinload(Task.subtasks).selectinload(Task.assignee),
    ]


class TaskRepository(BaseRepository[Task]):
    model = Task

    async def get(self, id: UUID) -> Task | None:
        stmt = select(Task).where(Task.id == id).options(*task_options())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        status: str | None = None,
        organisatie_eenheid_id: UUID | None = None,
        include_children: bool = False,
        opdracht_id: UUID | None = None,
        org_ctx: OrgContext | None = None,
    ) -> list[Task]:
        stmt = select(Task).options(*task_options()).offset(skip).limit(limit)
        if status is not None:
            stmt = stmt.where(Task.status == status)
        if organisatie_eenheid_id is not None:
            if include_children:
                unit_ids = await self._get_descendant_ids(organisatie_eenheid_id)
                stmt = stmt.where(Task.organisatie_eenheid_id.in_(unit_ids))
            else:
                stmt = stmt.where(Task.organisatie_eenheid_id == organisatie_eenheid_id)
        if opdracht_id is not None:
            stmt = stmt.where(Task.opdracht_id == opdracht_id)
        stmt = apply_task_filter(stmt, org_ctx)
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
                "node",
                "opdracht",
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
                "node",
                "opdracht",
                "subtasks",
            ],
        )
        return task

    async def get_by_opdracht(
        self,
        opdracht_id: UUID,
        skip: int = 0,
        limit: int = 100,
        org_ctx: OrgContext | None = None,
    ) -> list[Task]:
        stmt = (
            select(Task)
            .where(Task.opdracht_id == opdracht_id)
            .options(*task_options())
            .offset(skip)
            .limit(limit)
            .order_by(Task.created_at.desc())
        )
        stmt = apply_task_filter(stmt, org_ctx)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_assignee(
        self,
        assignee_id: UUID,
        skip: int = 0,
        limit: int = 100,
        org_ctx: OrgContext | None = None,
    ) -> list[Task]:
        stmt = (
            select(Task)
            .where(Task.assignee_id == assignee_id)
            .options(*task_options())
            .offset(skip)
            .limit(limit)
            .order_by(Task.created_at.desc())
        )
        # Your own tasks are always visible (``apply_task_filter``).
        stmt = apply_task_filter(stmt, org_ctx)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_node(
        self,
        node_id: UUID,
        skip: int = 0,
        limit: int = 100,
        org_ctx: OrgContext | None = None,
    ) -> list[Task]:
        stmt = (
            select(Task)
            .where(Task.node_id == node_id)
            .options(*task_options())
            .offset(skip)
            .limit(limit)
            .order_by(Task.created_at.desc())
        )
        stmt = apply_task_filter(stmt, org_ctx)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_overdue(
        self,
        assignee_id: UUID | None = None,
        *,
        org_ctx: OrgContext | None = None,
    ) -> list[Task]:
        stmt = (
            select(Task)
            .where(
                Task.deadline < date.today(),
                Task.status.notin_(["done", "cancelled"]),
            )
            .options(*task_options())
        )
        if assignee_id is not None:
            stmt = stmt.where(Task.assignee_id == assignee_id)
        # Your own tasks are always visible (``apply_task_filter``).
        stmt = apply_task_filter(stmt, org_ctx)
        stmt = stmt.order_by(Task.deadline.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_organisatie_eenheid(
        self,
        eenheid_id: UUID,
        include_children: bool = False,
        skip: int = 0,
        limit: int = 100,
        org_ctx: OrgContext | None = None,
    ) -> list[Task]:
        if include_children:
            unit_ids = await self._get_descendant_ids(eenheid_id)
            stmt = select(Task).where(Task.organisatie_eenheid_id.in_(unit_ids))
        else:
            stmt = select(Task).where(Task.organisatie_eenheid_id == eenheid_id)
        stmt = (
            stmt.options(*task_options())
            .offset(skip)
            .limit(limit)
            .order_by(Task.created_at.desc())
        )
        stmt = apply_task_filter(stmt, org_ctx)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_unassigned(
        self,
        organisatie_eenheid_id: UUID | None = None,
        *,
        org_ctx: OrgContext | None = None,
    ) -> list[Task]:
        stmt = (
            select(Task)
            .where(
                Task.assignee_id.is_(None),
                Task.status.notin_(["done", "cancelled"]),
            )
            .options(*task_options())
        )
        stmt = apply_task_filter(stmt, org_ctx)
        if organisatie_eenheid_id is not None:
            stmt = stmt.where(Task.organisatie_eenheid_id == organisatie_eenheid_id)
        stmt = stmt.order_by(Task.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_subtasks(
        self,
        parent_id: UUID,
        *,
        org_ctx: OrgContext | None = None,
    ) -> list[Task]:
        stmt = (
            select(Task)
            .where(Task.parent_id == parent_id)
            .options(*task_options())
            .order_by(Task.order.asc().nulls_last(), Task.created_at.asc())
        )
        stmt = apply_task_filter(stmt, org_ctx)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def reorder_subtasks(
        self,
        parent_id: UUID,
        task_ids: list[UUID],
        *,
        org_ctx: OrgContext | None = None,
    ) -> list[Task]:
        """Order the subtasks *org_ctx* sees as *task_ids* lists them.

        *task_ids* must be exactly the visible subtasks of the parent;
        subtasks the caller cannot see keep their order.  Returns the
        visible subtasks in their new order.  Raises ``ValueError`` with a
        message that names neither a subtask nor how many there are.
        """
        visible = await self.get_subtasks(parent_id, org_ctx=org_ctx)
        by_id = {t.id: t for t in visible}
        if len(task_ids) != len(set(task_ids)) or set(task_ids) != set(by_id):
            raise ValueError(REORDER_MISMATCH)
        for idx, tid in enumerate(task_ids):
            by_id[tid].order = idx
        await self.session.flush()
        return await self.get_subtasks(parent_id, org_ctx=org_ctx)

    async def get_distinct_work_types(
        self,
        *,
        org_ctx: OrgContext | None = None,
    ) -> list[str]:
        """Return all distinct non-null work_type values, sorted alphabetically."""
        stmt = (
            select(distinct(Task.work_type))
            .where(Task.work_type.isnot(None))
            .where(Task.work_type != "")
            .order_by(Task.work_type)
        )
        stmt = apply_task_filter(stmt, org_ctx)
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]

    async def _get_descendant_ids(self, root_id: UUID) -> list[UUID]:
        """Get all descendant unit IDs (including root) using a recursive CTE."""
        from bouwmeester.repositories.org_tree import get_descendant_ids

        return await get_descendant_ids(self.session, root_id)
