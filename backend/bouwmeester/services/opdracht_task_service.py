"""Service for automatic task generation on opdracht lifecycle events."""

import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.task import Task

logger = logging.getLogger(__name__)


class OpdrachtTaskService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Event-driven task creation
    # ------------------------------------------------------------------

    async def on_opdracht_created(self, opdracht: Opdracht) -> None:
        """Create tasks when a new opdracht is created."""
        await self._create_task_if_new(
            opdracht,
            work_type="Formalisatie",
            title=f"Opdracht formaliseren: {opdracht.titel}",
            priority="hoog",
        )

        if opdracht.type == "subsidie":
            await self._create_task_if_new(
                opdracht,
                work_type="Beschikking",
                title=f"Beschikkingsaanvraag indienen: {opdracht.titel}",
                priority="hoog",
            )

    async def on_status_changed(self, opdracht: Opdracht, old_status: str) -> None:
        """Create tasks on status transitions."""
        if opdracht.status == "afgerond" and old_status != "afgerond":
            await self._create_task_if_new(
                opdracht,
                work_type="Verantwoording",
                title=f"Verantwoording opstellen: {opdracht.titel}",
                priority="hoog",
            )

    # ------------------------------------------------------------------
    # Periodic checks (called from worker)
    # ------------------------------------------------------------------

    async def check_deadlines(self) -> int:
        """Create deadline-approaching tasks for opdrachten due within 30 days."""
        threshold = date.today() + timedelta(days=30)
        stmt = select(Opdracht).where(
            Opdracht.einddatum.isnot(None),
            Opdracht.einddatum <= threshold,
            Opdracht.status.in_(["concept", "actief"]),
        )
        result = await self.session.execute(stmt)
        opdrachten = list(result.scalars().all())

        count = 0
        for opdracht in opdrachten:
            created = await self._create_task_if_new(
                opdracht,
                work_type="Deadline",
                title=f"Deadline nadert: {opdracht.titel}",
                priority="hoog",
                deadline=opdracht.einddatum,
            )
            if created:
                count += 1

        if count:
            logger.info(f"Created {count} deadline-approaching tasks")
        return count

    async def check_budget_preparation(self) -> int:
        """Create budget preparation tasks in months 8-10 for active opdrachten."""
        today = date.today()
        if today.month not in (8, 9, 10):
            return 0

        next_year = today.year + 1
        stmt = select(Opdracht).where(
            Opdracht.status == "actief",
            Opdracht.begrotingsjaar == next_year,
        )
        result = await self.session.execute(stmt)
        opdrachten = list(result.scalars().all())

        count = 0
        for opdracht in opdrachten:
            created = await self._create_task_if_new(
                opdracht,
                work_type="Budgetvoorbereiding",
                title=f"Budget volgend jaar voorbereiden: {opdracht.titel}",
                priority="hoog",
            )
            if created:
                count += 1

        if count:
            logger.info(f"Created {count} budget preparation tasks")
        return count

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _has_open_task(self, opdracht_id, work_type: str) -> bool:
        """Check if an open task with this work_type already exists for the opdracht."""
        stmt = (
            select(Task.id)
            .where(
                Task.opdracht_id == opdracht_id,
                Task.work_type == work_type,
                Task.status.notin_(["done", "cancelled"]),
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _create_task_if_new(
        self,
        opdracht: Opdracht,
        *,
        work_type: str,
        title: str,
        priority: str = "normaal",
        deadline: date | None = None,
    ) -> bool:
        """Create a task for the opdracht if no open task with this work_type exists.

        Returns True if a task was created.
        """
        if await self._has_open_task(opdracht.id, work_type):
            return False

        task = Task(
            node_id=opdracht.instrument_id,
            opdracht_id=opdracht.id,
            title=title,
            priority=priority,
            status="open",
            work_type=work_type,
            assignee_id=opdracht.verantwoordelijke_id,
            deadline=deadline,
        )
        self.session.add(task)
        await self.session.flush()
        return True
