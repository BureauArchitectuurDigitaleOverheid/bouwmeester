"""Service layer for Notification operations."""

import asyncio
import logging
from collections import defaultdict
from datetime import date
from uuid import UUID

from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.org_context import OrgContext
from bouwmeester.core.permissions import PermissionContext
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.notification import Notification
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.person import Person
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.task import Task
from bouwmeester.repositories.notification import NotificationRepository
from bouwmeester.schema.notification import NotificationCreate
from bouwmeester.services.agent_rules import sender_may_instruct

logger = logging.getLogger(__name__)

# asyncio only holds weak references to tasks; keep them alive until done.
_BACKGROUND_TASKS: set[asyncio.Task] = set()


async def _mattermost_send_background(notification_id: UUID) -> None:
    """Send a notification to Mattermost in a background task.

    Uses its own DB session so the caller's request is not blocked.
    """
    logger.info("Mattermost background send starting for %s", notification_id)
    try:
        from bouwmeester.core.database import async_session
        from bouwmeester.services.mattermost_service import MattermostService

        async with async_session() as session:
            mm = MattermostService(session)
            try:
                if not await mm.is_enabled():
                    logger.debug(
                        "Mattermost disabled, skipping send for %s", notification_id
                    )
                    return
                notification = await session.get(Notification, notification_id)
                if notification:
                    sent = await mm.send_notification(notification)
                    logger.info(
                        "Mattermost send for %s: %s",
                        notification_id,
                        "ok" if sent else "skipped/failed",
                    )
                else:
                    logger.warning(
                        "Notification %s not found for Mattermost send",
                        notification_id,
                    )
            finally:
                await mm.close()
    except Exception:
        logger.exception(
            "Mattermost background send failed for notification %s",
            notification_id,
        )


# What a notification is about, as the read question its recipient must pass:
# ``(permission, resource type, resource id)``.
About = tuple[str, str, UUID]


def _about_related(data: NotificationCreate) -> About | None:
    """The item a notification names: the most specific related id.

    A task notification also links the task's node, but names the task.
    """
    if data.related_task_id is not None:
        return ("task:read", "task", data.related_task_id)
    if data.related_lead_id is not None:
        return ("lead:read", "lead", data.related_lead_id)
    if data.related_node_id is not None:
        return ("node:read", "corpus_node", data.related_node_id)
    return None


class NotificationService:
    """Creates notifications and forwards them to Mattermost.

    A notification names an item, so it only reaches recipients who may read
    it (``core.authz.can``).  Direct messages and replies carry the sender's
    own words and are not gated.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = NotificationRepository(session)
        # One permission context per recipient for the life of this service.
        self._contexts: dict[UUID, PermissionContext] = {}

    async def may_read(self, person_id: UUID, about: About) -> bool:
        """May *person_id* read the item *about* names?"""
        from bouwmeester.core.authz import can, perm_ctx_for

        ctx = self._contexts.get(person_id)
        if ctx is None:
            ctx = await perm_ctx_for(self.session, person_id)
            self._contexts[person_id] = ctx
        permission, resource_type, resource_id = about
        return await can(self.session, ctx, permission, resource_type, resource_id)

    async def send(
        self,
        data: NotificationCreate,
        *,
        about: About | None = None,
        actor_id: UUID | None = None,
    ) -> Notification | None:
        """Create a notification about an item and schedule Mattermost forwarding.

        *about* is the item the text names (default: read off the related
        ids).  Returns ``None`` when the recipient may not read it, or is an
        agent that *actor_id* (else the sender) may not instruct
        (``agent_rules``).
        """
        about = about or _about_related(data)
        if about is not None and not await self.may_read(data.person_id, about):
            return None
        if not await sender_may_instruct(
            self.session,
            actor_id or data.sender_id,
            await self.session.get(Person, data.person_id),
        ):
            return None
        return await self._create(data)

    async def _create(self, data: NotificationCreate) -> Notification:
        """Create and forward without a read check (messages between people)."""
        notification = await self.repo.create(data)
        self._send_to_mattermost(notification)
        return notification

    async def _send_all(
        self,
        items: list[NotificationCreate],
        *,
        about: About | None = None,
        actor_id: UUID | None = None,
    ) -> list[Notification]:
        sent = [await self.send(data, about=about, actor_id=actor_id) for data in items]
        return [n for n in sent if n is not None]

    async def _stakeholder_ids(
        self, node_ids: list[UUID], *, exclude: set[UUID] | None = None
    ) -> dict[UUID, list[UUID]]:
        """Person stakeholders per node, in grant order.

        Grants to an eenheid have no person to notify and are skipped.
        """
        stmt = select(
            ResourcePermission.resource_id, ResourcePermission.person_id
        ).where(
            ResourcePermission.resource_type == "corpus_node",
            ResourcePermission.resource_id.in_(node_ids),
            ResourcePermission.person_id.isnot(None),
        )
        if exclude:
            stmt = stmt.where(ResourcePermission.person_id.notin_(exclude))
        by_node: dict[UUID, list[UUID]] = defaultdict(list)
        for node_id, person_id in (await self.session.execute(stmt)).all():
            by_node[node_id].append(person_id)
        return by_node

    def _send_to_mattermost(self, notification: Notification) -> None:
        """Schedule Mattermost forwarding after the current transaction commits.

        The notification must already be flushed (have an id) before calling this.
        The background task uses its own DB session, so we defer it until
        after_commit to guarantee the notification is visible to the new session.
        """
        notification_id = notification.id
        sync_session = self.session.sync_session

        @event.listens_for(sync_session, "after_commit", once=True)
        def _after_commit(session):  # noqa: ARG001
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running event loop (e.g. in sync tests) — skip silently.
                return
            task = loop.create_task(_mattermost_send_background(notification_id))
            _BACKGROUND_TASKS.add(task)
            task.add_done_callback(_BACKGROUND_TASKS.discard)
            logger.debug("Scheduled Mattermost send for %s", notification_id)

    async def notify_task_assigned(
        self, task: Task, assignee: Person, actor_id: UUID | None = None
    ) -> Notification | None:
        # Don't notify if the actor is the assignee (self-assignment)
        if actor_id and assignee.id == actor_id:
            return None
        return await self.send(
            NotificationCreate(
                person_id=assignee.id,
                type="task_assigned",
                title=f"Nieuwe taak toegewezen: {task.title}",
                message=f"De taak '{task.title}' is aan je toegewezen.",
                related_node_id=task.node_id,
                related_task_id=task.id,
            ),
            actor_id=actor_id,
        )

    async def notify_node_updated(
        self, node: CorpusNode, actor: Person
    ) -> list[Notification]:
        """Notify all stakeholders of a node update (except the actor)."""
        by_node = await self._stakeholder_ids([node.id], exclude={actor.id})
        return await self._send_all(
            [
                NotificationCreate(
                    person_id=person_id,
                    type="node_updated",
                    title=f"Node bijgewerkt: {node.title}",
                    message=f"'{node.title}' is bijgewerkt door {actor.naam}.",
                    related_node_id=node.id,
                )
                for person_id in by_node.get(node.id, [])
            ],
            actor_id=actor.id,
        )

    async def notify_parlementair_item_imported(
        self,
        item_node: CorpusNode,
        affected_nodes: list[CorpusNode],
        item_type: str = "motie",
    ) -> list[Notification]:
        """Notify stakeholders about a new parliamentary item.

        One notification per person, naming the item and the first of their
        nodes it touches (their role on that node lets them read it).
        """
        if not affected_nodes:
            return []

        type_labels: dict[str, str] = {
            "motie": "aangenomen motie",
            "kamervraag": "kamervraag",
            "toezegging": "toezegging",
            "amendement": "amendement",
        }
        type_label = type_labels.get(item_type, item_type)
        node_map = {node.id: node for node in affected_nodes}

        first_node: dict[UUID, CorpusNode] = {}
        for node_id, person_ids in (
            await self._stakeholder_ids(list(node_map))
        ).items():
            for person_id in person_ids:
                first_node.setdefault(person_id, node_map[node_id])

        return await self._send_all(
            [
                NotificationCreate(
                    person_id=person_id,
                    type="politieke_input_imported",
                    title=f"Nieuw(e) {type_label}: {item_node.title}",
                    message=(
                        f"{type_label.capitalize()} '{item_node.title}' is mogelijk "
                        f"relevant voor '{node.title}'. "
                        f"Beoordeel de voorgestelde verbindingen."
                    ),
                    related_node_id=item_node.id,
                )
                for person_id, node in first_node.items()
            ]
        )

    async def notify_task_completed(
        self, task: Task, actor_id: UUID | None = None
    ) -> list[Notification]:
        """Notify assignee + node stakeholders when a task is completed."""
        recipients: list[UUID] = []
        if task.assignee_id:
            recipients.append(task.assignee_id)
        if task.node_id:
            recipients += (await self._stakeholder_ids([task.node_id])).get(
                task.node_id, []
            )
        return await self._send_all(
            [
                NotificationCreate(
                    person_id=person_id,
                    type="task_completed",
                    title=f"Taak afgerond: {task.title}",
                    message=f"De taak '{task.title}' is afgerond.",
                    related_node_id=task.node_id,
                    related_task_id=task.id,
                )
                for person_id in dict.fromkeys(recipients)
                if person_id != actor_id
            ],
            actor_id=actor_id,
        )

    async def notify_task_reassigned(
        self,
        task: Task,
        old_assignee_id: UUID,
        new_assignee: Person,
        actor_id: UUID | None = None,
    ) -> list[Notification]:
        """Notify old assignee (reassigned) and new assignee (assigned)."""
        return await self._send_all(
            [
                NotificationCreate(
                    person_id=old_assignee_id,
                    type="task_reassigned",
                    title=f"Taak overgedragen: {task.title}",
                    message=(
                        f"De taak '{task.title}' is overgedragen aan "
                        f"{new_assignee.naam}."
                    ),
                    related_node_id=task.node_id,
                    related_task_id=task.id,
                ),
                NotificationCreate(
                    person_id=new_assignee.id,
                    type="task_assigned",
                    title=f"Nieuwe taak toegewezen: {task.title}",
                    message=f"De taak '{task.title}' is aan je toegewezen.",
                    related_node_id=task.node_id,
                    related_task_id=task.id,
                ),
            ],
            actor_id=actor_id,
        )

    async def notify_edge_created(
        self,
        from_node: CorpusNode,
        to_node: CorpusNode,
        actor_id: UUID | None = None,
    ) -> list[Notification]:
        """Notify the stakeholders of both nodes about a new edge.

        A stakeholder of one end only hears the other end's title when they
        can read that node; otherwise the message names their own node only.
        Grants to an eenheid have no person to notify and are skipped.
        """
        nodes = {from_node.id: from_node, to_node.id: to_node}
        own_nodes: dict[UUID, set[UUID]] = defaultdict(set)
        for node_id, person_ids in (await self._stakeholder_ids(list(nodes))).items():
            for person_id in person_ids:
                if person_id != actor_id:
                    own_nodes[person_id].add(node_id)

        notifications: list[Notification] = []
        for person_id, own in own_nodes.items():
            # A stakeholder of both ends sees both.
            other = next((nid for nid in nodes if nid not in own), None)
            if other is None or await self.may_read(
                person_id, ("node:read", "corpus_node", other)
            ):
                title = f"Nieuwe verbinding: {from_node.title} - {to_node.title}"
                message = (
                    f"Er is een verbinding gelegd tussen "
                    f"'{from_node.title}' en '{to_node.title}'."
                )
                related = from_node.id
            else:
                node = nodes[next(iter(own))]
                title = f"Nieuwe verbinding: {node.title}"
                message = f"Er is een verbinding gelegd met '{node.title}'."
                related = node.id
            notification = await self.send(
                NotificationCreate(
                    person_id=person_id,
                    type="edge_created",
                    title=title,
                    message=message,
                    related_node_id=related,
                ),
                actor_id=actor_id,
            )
            if notification is not None:
                notifications.append(notification)
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
        return await self.send(
            NotificationCreate(
                person_id=person_id,
                type="stakeholder_added",
                title=f"Toegevoegd als {rol}: {node.title}",
                message=f"Je bent toegevoegd als {rol} aan '{node.title}'.",
                related_node_id=node.id,
            ),
            actor_id=actor_id,
        )

    async def notify_stakeholder_role_changed(
        self, node: CorpusNode, person_id: UUID, old_rol: str, new_rol: str
    ) -> Notification | None:
        """Notify a person that their stakeholder role changed."""
        return await self.send(
            NotificationCreate(
                person_id=person_id,
                type="stakeholder_role_changed",
                title=f"Rol gewijzigd: {node.title}",
                message=(
                    f"Je rol bij '{node.title}' is gewijzigd van {old_rol} "
                    f"naar {new_rol}."
                ),
                related_node_id=node.id,
            )
        )

    async def notify_team_manager(
        self, task: Task, eenheid_id: UUID, exclude_person_id: UUID | None = None
    ) -> Notification | None:
        """Notify the manager of an org unit about a task assignment."""
        from bouwmeester.repositories.organisatie_eenheid import (
            OrganisatieEenheidRepository,
        )

        manager = await OrganisatieEenheidRepository(self.session).get_unit_manager(
            eenheid_id
        )
        if manager is None:
            return None

        # Don't notify if the manager is the same as the assignee
        if exclude_person_id and manager.id == exclude_person_id:
            return None

        return await self.send(
            NotificationCreate(
                person_id=manager.id,
                type="task_assigned",
                title=f"Nieuwe taak in je eenheid: {task.title}",
                message=f"De taak '{task.title}' is toegewezen binnen jouw eenheid.",
                related_node_id=task.node_id,
                related_task_id=task.id,
            )
        )

    async def notify_direct_message(
        self,
        recipient: Person,
        sender: Person,
        message: str,
    ) -> tuple[Notification, Notification]:
        """Send a direct message. Returns (recipient_root, sender_root)."""
        is_agent = recipient.is_agent
        notif_type = "agent_prompt" if is_agent else "direct_message"
        label = "Prompt" if is_agent else "Bericht"

        # Recipient's root (unread)
        recipient_data = NotificationCreate(
            person_id=recipient.id,
            type=notif_type,
            title=f"{label} van {sender.naam}",
            message=message,
            sender_id=sender.id,
        )
        recipient_root = await self.repo.create(recipient_data)
        await self.session.flush()
        recipient_root.thread_id = recipient_root.id
        await self.session.flush()

        self._send_to_mattermost(recipient_root)

        # Sender's root (read — they sent it)
        sender_data = NotificationCreate(
            person_id=sender.id,
            type=notif_type,
            title=f"{label} aan {recipient.naam}",
            message=message,
            sender_id=sender.id,
            thread_id=recipient_root.id,
        )
        sender_root = await self.repo.create(sender_data)
        sender_root.is_read = True
        await self.session.flush()

        return recipient_root, sender_root

    async def notify_reply(
        self,
        recipient_id: UUID,
        sender: Person,
        message: str,
        thread_id: UUID,
        related_node_id: UUID | None = None,
        related_task_id: UUID | None = None,
    ) -> Notification:
        """Create a reply notification. Returns the reply.

        A reply carries the sender's own words, not an item's title, so it is
        not gated on the related ids it inherits from its thread.
        """
        return await self._create(
            NotificationCreate(
                person_id=recipient_id,
                type="direct_message",
                title=f"Reactie van {sender.naam}",
                message=message,
                sender_id=sender.id,
                parent_id=thread_id,
                related_node_id=related_node_id,
                related_task_id=related_task_id,
            )
        )

    async def notify_mention(
        self,
        mentioned_person_id: UUID,
        source_type: str,
        source_title: str,
        source_node_id: UUID | None = None,
        source_task_id: UUID | None = None,
        source_lead_id: UUID | None = None,
        sender_id: UUID | None = None,
    ) -> Notification | None:
        """Notify a person they were @mentioned.

        Being mentioned in an item gives no right to read it: someone who may
        not read the node, task or lead gets no notification (and so does not
        learn its title).
        """
        return await self.send(
            NotificationCreate(
                person_id=mentioned_person_id,
                type="mention",
                title=f"Je bent genoemd in: {source_title}",
                message=f"Je bent vermeld in '{source_title}'.",
                sender_id=sender_id,
                related_node_id=source_node_id,
                related_task_id=source_task_id,
                related_lead_id=source_lead_id,
            )
        )

    async def notify_access_request(self, email: str, naam: str) -> list[Notification]:
        """Notify all admin users about a new access request."""
        from bouwmeester.repositories.role import PersonRoleRepository

        admins = await PersonRoleRepository(self.session).get_super_admins()
        return await self._send_all(
            [
                NotificationCreate(
                    person_id=admin.id,
                    type="access_request",
                    title=f"Nieuw toegangsverzoek: {naam}",
                    message=f"{naam} ({email}) vraagt toegang aan tot Bouwmeester.",
                )
                for admin in admins
            ]
        )

    async def notify_placement_request(
        self, person_naam: str, eenheid_id: UUID, eenheid_naam: str
    ) -> list[Notification]:
        """Notify everyone who may decide the request, and all admins.

        That is every manager of the eenheid or of an eenheid above it
        (``core.authority.member_manager_ids``), not just the direct one.
        """
        from bouwmeester.core.authority import member_manager_ids
        from bouwmeester.repositories.role import PersonRoleRepository

        recipients = list(await member_manager_ids(self.session, eenheid_id))
        recipients += [
            admin.id
            for admin in await PersonRoleRepository(self.session).get_super_admins()
        ]
        return await self._send_all(
            [
                NotificationCreate(
                    person_id=person_id,
                    type="placement_request",
                    title=f"Teamverzoek: {person_naam}",
                    message=(
                        f"{person_naam} wil toegevoegd worden aan '{eenheid_naam}'."
                    ),
                )
                for person_id in dict.fromkeys(recipients)
            ]
        )

    async def _opdracht_recipients(
        self, opdracht: Opdracht, actor_id: UUID | None
    ) -> list[UUID]:
        """The verantwoordelijke, then the instrument's stakeholders."""
        recipients: list[UUID] = []
        if opdracht.verantwoordelijke_id:
            recipients.append(opdracht.verantwoordelijke_id)
        if opdracht.instrument_id:
            recipients += (await self._stakeholder_ids([opdracht.instrument_id])).get(
                opdracht.instrument_id, []
            )
        return [pid for pid in dict.fromkeys(recipients) if pid != actor_id]

    async def notify_opdracht_assigned(
        self, opdracht: Opdracht, actor_id: UUID | None = None
    ) -> list[Notification]:
        """Notify verantwoordelijke + instrument stakeholders who may read it."""
        items = []
        for person_id in await self._opdracht_recipients(opdracht, actor_id):
            if person_id == opdracht.verantwoordelijke_id:
                message = f"Je bent verantwoordelijke voor opdracht '{opdracht.titel}'."
            else:
                message = (
                    f"Opdracht '{opdracht.titel}' is aangemaakt "
                    f"voor een instrument waar je stakeholder bent."
                )
            items.append(
                NotificationCreate(
                    person_id=person_id,
                    type="opdracht_created",
                    title=f"Nieuwe opdracht: {opdracht.titel}",
                    message=message,
                    related_node_id=opdracht.instrument_id,
                )
            )
        return await self._send_all(
            items, about=("opdracht:read", "opdracht", opdracht.id), actor_id=actor_id
        )

    async def notify_opdracht_status_changed(
        self,
        opdracht: Opdracht,
        old_status: str,
        actor_id: UUID | None = None,
    ) -> list[Notification]:
        """Notify verantwoordelijke + stakeholders who may read the opdracht."""
        return await self._send_all(
            [
                NotificationCreate(
                    person_id=person_id,
                    type="opdracht_status_changed",
                    title=f"Opdracht status gewijzigd: {opdracht.titel}",
                    message=(
                        f"Status van '{opdracht.titel}' is gewijzigd "
                        f"van '{old_status}' naar '{opdracht.status}'."
                    ),
                    related_node_id=opdracht.instrument_id,
                )
                for person_id in await self._opdracht_recipients(opdracht, actor_id)
            ],
            about=("opdracht:read", "opdracht", opdracht.id),
            actor_id=actor_id,
        )

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

    async def get_dashboard_stats(
        self, person_id: UUID, org_ctx: OrgContext | None
    ) -> dict[str, int]:
        """Return dashboard statistics for a person.

        The corpus count is of the nodes *org_ctx* (the caller) sees.
        """
        from bouwmeester.repositories.corpus_node import CorpusNodeRepository

        corpus_node_count = await CorpusNodeRepository(self.session).count(
            org_ctx=org_ctx
        )

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

        # Active opdracht budget for this person (as verantwoordelijke)
        opdracht_result = await self.session.execute(
            select(func.coalesce(func.sum(Opdracht.budget), 0)).where(
                Opdracht.verantwoordelijke_id == person_id,
                Opdracht.status == "actief",
            )
        )
        active_opdracht_budget = float(opdracht_result.scalar_one())

        return {
            "corpus_node_count": corpus_node_count,
            "open_task_count": open_task_count,
            "overdue_task_count": overdue_task_count,
            "active_opdracht_budget": active_opdracht_budget,
        }
