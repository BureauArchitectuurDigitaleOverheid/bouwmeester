"""Handlers for Mattermost slash commands and interactive button actions."""

import logging
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.core.config import get_settings
from bouwmeester.core.query_utils import escape_like
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.task import Task
from bouwmeester.repositories.mattermost_user import MattermostUserRepository
from bouwmeester.repositories.search import SearchRepository
from bouwmeester.services.mattermost_utils import escape_mattermost_md as _escape_md

logger = logging.getLogger(__name__)


class MattermostSlashService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = MattermostUserRepository(session)

    async def _resolve_person_id(self, mattermost_user_id: str) -> UUID | None:
        """Resolve a Mattermost user ID to a Bouwmeester person ID."""
        mapping = await self.repo.get_by_mattermost_user_id(mattermost_user_id)
        return mapping.person_id if mapping else None

    async def handle_command(self, mattermost_user_id: str, command_text: str) -> dict:
        """Route a /bouwmeester slash command to the right handler."""
        parts = command_text.split(maxsplit=1)
        subcommand = parts[0].lower() if parts else "help"
        args = parts[1].strip() if len(parts) > 1 else ""

        handlers = {
            "taken": self._handle_taken,
            "zoek": self._handle_zoek,
            "status": self._handle_status,
            "help": self._handle_help,
        }

        handler = handlers.get(subcommand, self._handle_help)
        return await handler(mattermost_user_id, args)

    async def _handle_taken(self, mattermost_user_id: str, args: str) -> dict:
        """List the user's open tasks, optionally filtered by deadline."""
        person_id = await self._resolve_person_id(mattermost_user_id)
        if not person_id:
            return _ephemeral(
                "Je Mattermost-account is niet gekoppeld aan Bouwmeester. "
                "Ga naar Instellingen in Bouwmeester om te koppelen."
            )

        today = date.today()

        stmt = (
            select(Task)
            .where(
                Task.assignee_id == person_id,
                Task.status.in_(["open", "in_progress"]),
            )
            .options(selectinload(Task.node))
            .order_by(Task.deadline.asc().nulls_last())
        )

        # Apply deadline filter.
        filter_arg = args.lower() if args else "alles"
        if filter_arg == "vandaag":
            stmt = stmt.where(Task.deadline <= today)
        elif filter_arg == "week":
            stmt = stmt.where(Task.deadline <= today + timedelta(days=7))
        # "alles" = no deadline filter

        result = await self.session.execute(stmt)
        tasks = result.scalars().all()

        if not tasks:
            return _ephemeral("Geen open taken gevonden.")

        frontend_url = get_settings().FRONTEND_URL.rstrip("/")
        lines = [f"**Jouw taken** ({len(tasks)}):\n"]
        for t in tasks[:20]:
            deadline_str = (
                t.deadline.strftime("%d-%m") if t.deadline else "geen deadline"
            )
            status_icon = (
                ":red_circle:"
                if t.deadline and t.deadline < today
                else ":large_blue_circle:"
            )
            node_name = _escape_md(t.node.title) if t.node else ""
            link = f"{frontend_url}/taken?task={t.id}"
            lines.append(
                f"{status_icon} [{_escape_md(t.title)}]({link}) — {deadline_str}"
                + (f" ({node_name})" if node_name else "")
            )

        if len(tasks) > 20:
            lines.append(f"\n_...en {len(tasks) - 20} meer_")

        return _ephemeral("\n".join(lines))

    async def _handle_zoek(self, mattermost_user_id: str, args: str) -> dict:
        """Full-text search in the corpus."""
        if not args:
            return _ephemeral("Gebruik: `/bouwmeester zoek <zoekterm>`")

        person_id = await self._resolve_person_id(mattermost_user_id)
        if not person_id:
            return _ephemeral(
                "Je account is niet gekoppeld. Ga naar Instellingen in Bouwmeester."
            )

        search_repo = SearchRepository(self.session)
        results = await search_repo.full_text_search(
            query=args, result_types=["corpus_node"], limit=10
        )

        if not results:
            return _ephemeral(f"Geen resultaten gevonden voor '{_escape_md(args)}'.")

        frontend_url = get_settings().FRONTEND_URL.rstrip("/")
        lines = [f"**Zoekresultaten** voor '{_escape_md(args)}':\n"]
        for r in results:
            url = f"{frontend_url}{r['url']}"
            subtitle = f" ({_escape_md(r['subtitle'])})" if r.get("subtitle") else ""
            lines.append(f"- [{_escape_md(r['title'])}]({url}){subtitle}")

        return _ephemeral("\n".join(lines))

    async def _handle_status(self, mattermost_user_id: str, args: str) -> dict:
        """Show status of a dossier (open/total task counts)."""
        if not args:
            return _ephemeral("Gebruik: `/bouwmeester status <dossiernaam>`")

        person_id = await self._resolve_person_id(mattermost_user_id)
        if not person_id:
            return _ephemeral(
                "Je account is niet gekoppeld. Ga naar Instellingen in Bouwmeester."
            )

        # Find dossier by title search.
        escaped_args = escape_like(args)
        stmt = (
            select(CorpusNode)
            .where(
                CorpusNode.node_type == "dossier",
                CorpusNode.title.ilike(f"%{escaped_args}%"),
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        dossier = result.scalar_one_or_none()

        if not dossier:
            return _ephemeral(f"Geen dossier gevonden met '{_escape_md(args)}'.")

        # Count tasks for this dossier.
        from sqlalchemy import func

        task_stats = await self.session.execute(
            select(
                func.count(Task.id).label("total"),
                func.count(Task.id)
                .filter(Task.status.in_(["open", "in_progress"]))
                .label("open"),
            ).where(Task.node_id == dossier.id)
        )
        row = task_stats.one()

        frontend_url = get_settings().FRONTEND_URL.rstrip("/")
        link = f"{frontend_url}/nodes/{dossier.id}"

        return _ephemeral(
            f"**[{_escape_md(dossier.title)}]({link})**\n"
            f"- Open taken: {row.open}\n"
            f"- Totaal taken: {row.total}\n"
        )

    async def _handle_help(self, mattermost_user_id: str, args: str) -> dict:
        """Show available commands."""
        return _ephemeral(
            "**Bouwmeester commando's:**\n"
            "- `/bouwmeester taken [vandaag|week|alles]` — Jouw open taken\n"
            "- `/bouwmeester zoek <term>` — Zoek in het corpus\n"
            "- `/bouwmeester status <dossier>` — Status van een dossier\n"
            "- `/bouwmeester help` — Dit overzicht\n"
        )

    # ---------------------------------------------------------------------------
    # Interactive button actions
    # ---------------------------------------------------------------------------

    async def handle_action(
        self, mattermost_user_id: str, action: str, context: dict
    ) -> dict:
        """Handle an interactive button click."""
        if action == "complete_task":
            return await self._action_complete_task(mattermost_user_id, context)
        return {"ephemeral_text": "Onbekende actie."}

    async def _action_complete_task(
        self, mattermost_user_id: str, context: dict
    ) -> dict:
        """Complete a task from a Mattermost button click."""
        person_id = await self._resolve_person_id(mattermost_user_id)
        if not person_id:
            return {"ephemeral_text": "Je account is niet gekoppeld."}

        task_id_str = context.get("task_id")
        if not task_id_str:
            return {"ephemeral_text": "Geen taak-ID gevonden."}

        try:
            task_id = UUID(task_id_str)
        except (ValueError, AttributeError):
            return {"ephemeral_text": "Ongeldig taak-ID."}
        task = await self.session.get(Task, task_id)
        if not task:
            return {"ephemeral_text": "Taak niet gevonden."}

        # Verify the user is the assignee.
        if task.assignee_id != person_id:
            return {"ephemeral_text": "Je bent niet de toegewezene van deze taak."}

        if task.status == "done":
            return {"ephemeral_text": "Deze taak is al afgerond."}

        # Complete the task.
        task.status = "done"
        await self.session.flush()

        # Log activity.
        from bouwmeester.services.activity_service import ActivityService

        activity_service = ActivityService(self.session)
        await activity_service.log_event(
            event_type="task.completed",
            actor_id=person_id,
            task_id=task.id,
            node_id=task.node_id,
            details={"completed_from": "mattermost"},
        )

        # Trigger completion notifications.
        from bouwmeester.services.notification_service import NotificationService

        notif_service = NotificationService(self.session)
        await notif_service.notify_task_completed(task, actor_id=person_id)

        escaped_title = _escape_md(task.title)
        return {
            "update": {
                "message": f"Taak afgerond: **{escaped_title}**",
                "props": {
                    "attachments": [
                        {
                            "color": "#22C55E",
                            "text": f"Taak '{escaped_title}' is afgerond.",
                        }
                    ],
                },
            },
        }


def _ephemeral(text: str) -> dict:
    """Build an ephemeral (only visible to requester) response."""
    return {"response_type": "ephemeral", "text": text}
