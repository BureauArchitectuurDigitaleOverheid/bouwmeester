"""Service layer for Notification operations."""

from collections import defaultdict
from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.node_stakeholder import NodeStakeholder
from bouwmeester.models.notification import Notification
from bouwmeester.models.org_manager import OrganisatieEenheidManager
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.task import Task
from bouwmeester.repositories.notification import NotificationRepository
from bouwmeester.schema.notification import NotificationCreate


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = NotificationRepository(session)

    async def notify_task_assigned(
        self, task: Task, assignee: Person, actor_id: UUID | None = None
    ) -> Notification | None:
        # Don't notify if the actor is the assignee (self-assignment)
        if actor_id and assignee.id == actor_id:
            return None
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

    async def notify_parlementair_item_imported(
        self,
        item_node: CorpusNode,
        affected_nodes: list[CorpusNode],
        item_type: str = "motie",
    ) -> list[Notification]:
        """Notify stakeholders about a new parliamentary item."""
        if not affected_nodes:
            return []

        type_labels: dict[str, str] = {
            "motie": "aangenomen motie",
            "kamervraag": "kamervraag",
            "toezegging": "toezegging",
            "amendement": "amendement",
        }
        type_label = type_labels.get(item_type, item_type)

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
                    title=f"Nieuw(e) {type_label}: {item_node.title}",
                    message=(
                        f"{type_label.capitalize()} '{item_node.title}' is mogelijk "
                        f"relevant voor '{node.title}'. "
                        f"Beoordeel de voorgestelde verbindingen."
                    ),
                    related_node_id=item_node.id,
                )
                notification = await self.repo.create(data)
                notifications.append(notification)

        return notifications

    async def notify_task_completed(
        self, task: Task, actor_id: UUID | None = None
    ) -> list[Notification]:
        """Notify assignee + node stakeholders when a task is completed."""
        notifications: list[Notification] = []
        notified_ids: set[UUID] = set()

        # Skip the person who completed the task
        if actor_id:
            notified_ids.add(actor_id)

        # Notify assignee
        if task.assignee_id and task.assignee_id not in notified_ids:
            notified_ids.add(task.assignee_id)
            data = NotificationCreate(
                person_id=task.assignee_id,
                type="task_completed",
                title=f"Taak afgerond: {task.title}",
                message=f"De taak '{task.title}' is afgerond.",
                related_node_id=task.node_id,
                related_task_id=task.id,
            )
            notifications.append(await self.repo.create(data))

        # Notify node stakeholders
        if task.node_id:
            stmt = select(NodeStakeholder).where(
                NodeStakeholder.node_id == task.node_id,
                NodeStakeholder.person_id.notin_(notified_ids),
            )
            result = await self.session.execute(stmt)
            for sh in result.scalars().all():
                notified_ids.add(sh.person_id)
                data = NotificationCreate(
                    person_id=sh.person_id,
                    type="task_completed",
                    title=f"Taak afgerond: {task.title}",
                    message=f"De taak '{task.title}' is afgerond.",
                    related_node_id=task.node_id,
                    related_task_id=task.id,
                )
                notifications.append(await self.repo.create(data))

        return notifications

    async def notify_task_reassigned(
        self, task: Task, old_assignee_id: UUID, new_assignee: Person
    ) -> list[Notification]:
        """Notify old assignee (reassigned) and new assignee (assigned)."""
        notifications: list[Notification] = []

        # Notify old assignee
        data = NotificationCreate(
            person_id=old_assignee_id,
            type="task_reassigned",
            title=f"Taak overgedragen: {task.title}",
            message=f"De taak '{task.title}' is overgedragen aan {new_assignee.naam}.",
            related_node_id=task.node_id,
            related_task_id=task.id,
        )
        notifications.append(await self.repo.create(data))

        # Notify new assignee
        data = NotificationCreate(
            person_id=new_assignee.id,
            type="task_assigned",
            title=f"Nieuwe taak toegewezen: {task.title}",
            message=f"De taak '{task.title}' is aan je toegewezen.",
            related_node_id=task.node_id,
            related_task_id=task.id,
        )
        notifications.append(await self.repo.create(data))

        return notifications

    async def notify_edge_created(
        self,
        from_node: CorpusNode,
        to_node: CorpusNode,
        actor_id: UUID | None = None,
    ) -> list[Notification]:
        """Notify stakeholders of both nodes about a new edge."""
        node_ids = [from_node.id, to_node.id]
        stmt = select(NodeStakeholder).where(
            NodeStakeholder.node_id.in_(node_ids),
        )
        result = await self.session.execute(stmt)
        all_stakeholders = result.scalars().all()

        notifications: list[Notification] = []
        notified_ids: set[UUID] = set()
        if actor_id:
            notified_ids.add(actor_id)

        for sh in all_stakeholders:
            if sh.person_id in notified_ids:
                continue
            notified_ids.add(sh.person_id)
            data = NotificationCreate(
                person_id=sh.person_id,
                type="edge_created",
                title=f"Nieuwe verbinding: {from_node.title} — {to_node.title}",
                message=(
                    f"Er is een verbinding gelegd tussen "
                    f"'{from_node.title}' en '{to_node.title}'."
                ),
                related_node_id=from_node.id,
            )
            notifications.append(await self.repo.create(data))

        return notifications

    async def notify_stakeholder_added(
        self,
        node: CorpusNode,
        person_id: UUID,
        rol: str,
        actor_id: UUID | None = None,
    ) -> Notification | None:
        """Notify a person that they were added as stakeholder."""
        # Don't notify if person added themselves
        if actor_id and person_id == actor_id:
            return None
        data = NotificationCreate(
            person_id=person_id,
            type="stakeholder_added",
            title=f"Toegevoegd als {rol}: {node.title}",
            message=f"Je bent toegevoegd als {rol} aan '{node.title}'.",
            related_node_id=node.id,
        )
        return await self.repo.create(data)

    async def notify_stakeholder_role_changed(
        self, node: CorpusNode, person_id: UUID, old_rol: str, new_rol: str
    ) -> Notification:
        """Notify a person that their stakeholder role changed."""
        data = NotificationCreate(
            person_id=person_id,
            type="stakeholder_role_changed",
            title=f"Rol gewijzigd: {node.title}",
            message=(
                f"Je rol bij '{node.title}' is gewijzigd van {old_rol} naar {new_rol}."
            ),
            related_node_id=node.id,
        )
        return await self.repo.create(data)

    async def notify_team_manager(
        self, task: Task, eenheid_id: UUID, exclude_person_id: UUID | None = None
    ) -> Notification | None:
        """Notify the manager of an org unit about a task assignment.

        Uses temporal manager record first, falls back to legacy manager_id.
        """
        today = date.today()

        # Try temporal manager record
        stmt = select(OrganisatieEenheidManager).where(
            OrganisatieEenheidManager.eenheid_id == eenheid_id,
            OrganisatieEenheidManager.geldig_van <= today,
            (OrganisatieEenheidManager.geldig_tot.is_(None))
            | (OrganisatieEenheidManager.geldig_tot >= today),
        )
        result = await self.session.execute(stmt)
        manager_record = result.scalar_one_or_none()

        manager_id: UUID | None = None
        if manager_record and manager_record.manager_id:
            manager_id = manager_record.manager_id
        else:
            # Fallback to legacy manager_id on OrganisatieEenheid
            eenheid = await self.session.get(OrganisatieEenheid, eenheid_id)
            if eenheid and eenheid.manager_id:
                manager_id = eenheid.manager_id

        if not manager_id:
            return None

        # Don't notify if the manager is the same as the assignee
        if exclude_person_id and manager_id == exclude_person_id:
            return None

        data = NotificationCreate(
            person_id=manager_id,
            type="task_assigned",
            title=f"Nieuwe taak in je eenheid: {task.title}",
            message=f"De taak '{task.title}' is toegewezen binnen jouw eenheid.",
            related_node_id=task.node_id,
            related_task_id=task.id,
        )
        return await self.repo.create(data)

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

    async def notify_access_request(self, email: str, naam: str) -> list[Notification]:
        """Notify all admin users about a new access request."""
        stmt = select(Person).where(Person.is_admin == True)  # noqa: E712
        result = await self.session.execute(stmt)
        admins = result.scalars().all()

        notifications: list[Notification] = []
        for admin in admins:
            data = NotificationCreate(
                person_id=admin.id,
                type="access_request",
                title=f"Nieuw toegangsverzoek: {naam}",
                message=f"{naam} ({email}) vraagt toegang aan tot Bouwmeester.",
            )
            notifications.append(await self.repo.create(data))
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

    async def get_dashboard_stats(self, person_id: UUID) -> dict[str, int]:
        """Return dashboard statistics for a person."""
        # Total corpus nodes
        node_result = await self.session.execute(select(func.count(CorpusNode.id)))
        corpus_node_count = node_result.scalar_one()

        # Open tasks assigned to this person
        open_result = await self.session.execute(
            select(func.count(Task.id)).where(
                Task.assignee_id == person_id,
                Task.status.in_(["open", "in_progress"]),
            )
        )
        open_task_count = open_result.scalar_one()

        # Overdue tasks assigned to this person
        today = date.today()
        overdue_result = await self.session.execute(
            select(func.count(Task.id)).where(
                Task.assignee_id == person_id,
                Task.deadline < today,
                Task.status.notin_(["done", "cancelled"]),
            )
        )
        overdue_task_count = overdue_result.scalar_one()

        return {
            "corpus_node_count": corpus_node_count,
            "open_task_count": open_task_count,
            "overdue_task_count": overdue_task_count,
        }
