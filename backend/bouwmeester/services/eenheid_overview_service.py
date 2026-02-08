"""Service for eenheid task overview — batched queries, no N+1."""

from collections import defaultdict
from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.task import Task
from bouwmeester.repositories.org_tree import get_descendant_ids
from bouwmeester.schema.task import (
    EenheidOverviewResponse,
    EenheidPersonTaskStats,
    EenheidSubeenheidStats,
)


class EenheidOverviewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_overview(
        self, organisatie_eenheid_id: UUID
    ) -> EenheidOverviewResponse:
        all_unit_ids = await get_descendant_ids(self.session, organisatie_eenheid_id)

        unassigned_count = await self._unassigned_count(all_unit_ids)
        by_person = await self._person_stats(organisatie_eenheid_id)
        by_subeenheid = await self._subeenheid_stats(
            organisatie_eenheid_id, all_unit_ids
        )

        return EenheidOverviewResponse(
            unassigned_count=unassigned_count,
            by_person=by_person,
            by_subeenheid=by_subeenheid,
        )

    async def _unassigned_count(self, unit_ids: list[UUID]) -> int:
        stmt = (
            select(func.count())
            .select_from(Task)
            .where(
                Task.organisatie_eenheid_id.in_(unit_ids),
                Task.assignee_id.is_(None),
                Task.status.notin_(["done", "cancelled"]),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def _person_stats(self, eenheid_id: UUID) -> list[EenheidPersonTaskStats]:
        # Get people in this unit (active placements)
        people_stmt = (
            select(Person.id, Person.naam)
            .join(
                PersonOrganisatieEenheid,
                PersonOrganisatieEenheid.person_id == Person.id,
            )
            .where(
                PersonOrganisatieEenheid.organisatie_eenheid_id == eenheid_id,
                PersonOrganisatieEenheid.eind_datum.is_(None),
            )
            .order_by(Person.naam)
        )
        people_result = await self.session.execute(people_stmt)
        people = people_result.all()

        if not people:
            return []

        person_ids = [p.id for p in people]

        # Batch: get all task stats for these people in one query
        stats_stmt = (
            select(
                Task.assignee_id,
                Task.status,
                Task.deadline,
                func.count().label("cnt"),
            )
            .where(Task.assignee_id.in_(person_ids))
            .group_by(Task.assignee_id, Task.status, Task.deadline)
        )
        stats_result = await self.session.execute(stats_stmt)

        # Aggregate per person
        today = date.today()
        counts: dict[UUID, dict[str, int]] = defaultdict(
            lambda: {
                "open": 0,
                "in_progress": 0,
                "done": 0,
                "overdue": 0,
            }
        )
        for assignee_id, task_status, deadline, cnt in stats_result.all():
            c = counts[assignee_id]
            if task_status == "open":
                c["open"] += cnt
            elif task_status == "in_progress":
                c["in_progress"] += cnt
            elif task_status == "done":
                c["done"] += cnt
            if (
                task_status in ("open", "in_progress")
                and deadline is not None
                and deadline < today
            ):
                c["overdue"] += cnt

        return [
            EenheidPersonTaskStats(
                person_id=p.id,
                person_naam=p.naam,
                open_count=counts[p.id]["open"],
                in_progress_count=counts[p.id]["in_progress"],
                done_count=counts[p.id]["done"],
                overdue_count=counts[p.id]["overdue"],
            )
            for p in people
        ]

    async def _subeenheid_stats(
        self, parent_id: UUID, all_unit_ids: list[UUID]
    ) -> list[EenheidSubeenheidStats]:
        # Get direct children
        children_stmt = (
            select(OrganisatieEenheid)
            .where(OrganisatieEenheid.parent_id == parent_id)
            .order_by(OrganisatieEenheid.naam)
        )
        children_result = await self.session.execute(children_stmt)
        children = list(children_result.scalars().all())

        if not children:
            return []

        # Get descendants for each child using the shared utility
        child_id_sets: dict[UUID, list[UUID]] = {}
        for child in children:
            child_id_sets[child.id] = await get_descendant_ids(self.session, child.id)

        # Batch: get all task stats for all descendant units in one query
        stats_stmt = (
            select(
                Task.organisatie_eenheid_id,
                Task.status,
                func.count().label("cnt"),
            )
            .where(Task.organisatie_eenheid_id.in_(all_unit_ids))
            .group_by(Task.organisatie_eenheid_id, Task.status)
        )
        stats_result = await self.session.execute(stats_stmt)

        # Index stats by unit_id
        unit_stats: dict[UUID, dict[str, int]] = defaultdict(
            lambda: {"open": 0, "in_progress": 0, "done": 0}
        )
        for unit_id, task_status, cnt in stats_result.all():
            unit_stats[unit_id][task_status] = cnt

        # Aggregate per child (sum over its descendants)
        result: list[EenheidSubeenheidStats] = []
        for child in children:
            open_c = 0
            ip_c = 0
            done_c = 0
            for desc_id in child_id_sets[child.id]:
                s = unit_stats.get(desc_id, {})
                open_c += s.get("open", 0)
                ip_c += s.get("in_progress", 0)
                done_c += s.get("done", 0)

            result.append(
                EenheidSubeenheidStats(
                    eenheid_id=child.id,
                    eenheid_naam=child.naam,
                    eenheid_type=child.type,
                    open_count=open_c,
                    in_progress_count=ip_c,
                    done_count=done_c,
                )
            )

        return result
