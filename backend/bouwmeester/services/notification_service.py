"""Service layer for Notification operations."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.notification import Notification
from bouwmeester.models.person import Person
from bouwmeester.models.task import Task
from bouwmeester.repositories.notification import NotificationRepository
from bouwmeester.schema.notification import NotificationCreate


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = NotificationRepository(session)

    async def notify_task_assigned(self, task: Task, assignee: Person) -> Notification:
        data = NotificationCreate(
            person_id=assignee.id,
            type="task_assigned",
            title=f"Nieuwe taak toegewezen: {task.title}",
            message=f"De taak '{task.title}' is aan je toegewezen.",
            related_node_id=task.node_id,
            related_task_id=task.id,
        )
        return await self.repo.create(data)

    async def notify_task_overdue(self, task: Task) -> Notification | None:
        if task.assignee_id is None:
            return None
        data = NotificationCreate(
            person_id=task.assignee_id,
            type="task_overdue",
            title=f"Taak te laat: {task.title}",
            message=f"De deadline voor taak '{task.title}' is verstreken.",
            related_node_id=task.node_id,
            related_task_id=task.id,
        )
        return await self.repo.create(data)

    async def notify_node_updated(
        self, node: CorpusNode, actor: Person
    ) -> list[Notification]:
        """Notify all stakeholders of a node update (except the actor)."""
        from sqlalchemy import select

        from bouwmeester.models.node_stakeholder import NodeStakeholder

        stmt = select(NodeStakeholder).where(
            NodeStakeholder.node_id == node.id,
            NodeStakeholder.person_id != actor.id,
        )
        result = await self.session.execute(stmt)
        stakeholders = result.scalars().all()

        notifications = []
        for sh in stakeholders:
            data = NotificationCreate(
                person_id=sh.person_id,
                type="node_updated",
                title=f"Node bijgewerkt: {node.title}",
                message=f"'{node.title}' is bijgewerkt door {actor.naam}.",
                related_node_id=node.id,
            )
            notification = await self.repo.create(data)
            notifications.append(notification)
        return notifications

    async def notify_coverage_needed(
        self, absent_person: Person, nodes: list[CorpusNode]
    ) -> list[Notification]:
        """Notify relevant people that coverage is needed because someone is absent."""
        notifications = []
        for node in nodes:
            from sqlalchemy import select

            from bouwmeester.models.node_stakeholder import NodeStakeholder

            stmt = select(NodeStakeholder).where(
                NodeStakeholder.node_id == node.id,
                NodeStakeholder.person_id != absent_person.id,
            )
            result = await self.session.execute(stmt)
            stakeholders = result.scalars().all()

            for sh in stakeholders:
                data = NotificationCreate(
                    person_id=sh.person_id,
                    type="coverage_needed",
                    title=f"Vervanging nodig: {node.title}",
                    message=(
                        f"{absent_person.naam} is afwezig. "
                        f"Vervanging is nodig voor '{node.title}'."
                    ),
                    related_node_id=node.id,
                )
                notification = await self.repo.create(data)
                notifications.append(notification)
        return notifications

    async def get_notifications(
        self,
        person_id: UUID,
        unread_only: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Notification]:
        return await self.repo.get_by_person(
            person_id, unread_only=unread_only, skip=skip, limit=limit
        )

    async def mark_read(self, notification_id: UUID) -> Notification | None:
        return await self.repo.mark_read(notification_id)

    async def mark_all_read(self, person_id: UUID) -> int:
        return await self.repo.mark_all_read(person_id)

    async def count_unread(self, person_id: UUID) -> int:
        return await self.repo.count_unread(person_id)
