"""Service layer for Notification operations."""

from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.node_stakeholder import NodeStakeholder
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
        if not nodes:
            return []

        node_ids = [node.id for node in nodes]
        node_map = {node.id: node for node in nodes}

        stmt = select(NodeStakeholder).where(
            NodeStakeholder.node_id.in_(node_ids),
            NodeStakeholder.person_id != absent_person.id,
        )
        result = await self.session.execute(stmt)
        all_stakeholders = result.scalars().all()

        stakeholders_by_node: dict[UUID, list[NodeStakeholder]] = defaultdict(list)
        for sh in all_stakeholders:
            stakeholders_by_node[sh.node_id].append(sh)

        notifications = []
        for node_id, stakeholders in stakeholders_by_node.items():
            node = node_map[node_id]
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

    async def notify_motie_imported(
        self, motie_node: CorpusNode, affected_nodes: list[CorpusNode]
    ) -> list[Notification]:
        """Notify stakeholders of affected nodes about a new imported motie."""
        if not affected_nodes:
            return []

        node_ids = [node.id for node in affected_nodes]
        node_map = {node.id: node for node in affected_nodes}

        stmt = select(NodeStakeholder).where(
            NodeStakeholder.node_id.in_(node_ids),
        )
        result = await self.session.execute(stmt)
        all_stakeholders = result.scalars().all()

        stakeholders_by_node: dict[UUID, list[NodeStakeholder]] = defaultdict(list)
        for sh in all_stakeholders:
            stakeholders_by_node[sh.node_id].append(sh)

        notifications = []
        notified_person_ids: set[UUID] = set()

        for node_id, stakeholders in stakeholders_by_node.items():
            node = node_map[node_id]
            for sh in stakeholders:
                if sh.person_id in notified_person_ids:
                    continue
                notified_person_ids.add(sh.person_id)

                data = NotificationCreate(
                    person_id=sh.person_id,
                    type="politieke_input_imported",
                    title=f"Nieuwe aangenomen motie: {motie_node.title}",
                    message=(
                        f"Aangenomen motie '{motie_node.title}' is mogelijk "
                        f"relevant voor '{node.title}'. "
                        f"Beoordeel de voorgestelde verbindingen."
                    ),
                    related_node_id=motie_node.id,
                )
                notification = await self.repo.create(data)
                notifications.append(notification)

        return notifications

    async def notify_mention(
        self,
        mentioned_person_id: UUID,
        source_type: str,
        source_title: str,
        source_node_id: UUID | None = None,
        source_task_id: UUID | None = None,
        sender_id: UUID | None = None,
    ) -> Notification:
        """Notify a person they were @mentioned."""
        data = NotificationCreate(
            person_id=mentioned_person_id,
            type="mention",
            title=f"Je bent genoemd in: {source_title}",
            message=f"Je bent vermeld in '{source_title}'.",
            sender_id=sender_id,
            related_node_id=source_node_id,
            related_task_id=source_task_id,
        )
        return await self.repo.create(data)

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
