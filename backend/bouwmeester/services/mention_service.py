"""Service layer for mention extraction, syncing, and notification."""

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.mention import Mention
from bouwmeester.models.task import Task
from bouwmeester.repositories.mention import MentionRepository
from bouwmeester.schema.mention import (
    MentionCreate,
    MentionReference,
    MentionSearchResult,
)


class MentionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = MentionRepository(session)

    @staticmethod
    def extract_mentions(description_json: str) -> list[dict]:
        """Parse TipTap JSON and extract mention nodes.

        Returns list of dicts with keys: mention_type, target_id.
        mention_type is 'person' for @mentions, derived from attrs for #mentions.
        """
        if not description_json:
            return []

        try:
            doc = json.loads(description_json)
        except (json.JSONDecodeError, TypeError):
            return []

        mentions: list[dict] = []
        _walk_tiptap(doc, mentions)
        return mentions

    async def sync_mentions(
        self,
        source_type: str,
        source_id: UUID,
        description_json: str | None,
        created_by: UUID | None,
    ) -> list[Mention]:
        """Sync mentions for source. Returns only genuinely new mentions."""
        # Get existing mentions before deleting
        existing = await self.repo.get_by_source(source_type, source_id)
        existing_keys: set[tuple[str, str]] = {
            (m.mention_type, str(m.target_id)) for m in existing
        }

        await self.repo.delete_by_source(source_type, source_id)

        if not description_json:
            return []

        raw_mentions = self.extract_mentions(description_json)
        if not raw_mentions:
            return []

        # Deduplicate by (mention_type, target_id)
        seen: set[tuple[str, str]] = set()
        creates: list[MentionCreate] = []
        for m in raw_mentions:
            key = (m["mention_type"], m["target_id"])
            if key in seen:
                continue
            seen.add(key)
            creates.append(
                MentionCreate(
                    source_type=source_type,
                    source_id=source_id,
                    mention_type=m["mention_type"],
                    target_id=UUID(m["target_id"]),
                    created_by=created_by,
                )
            )

        if not creates:
            return []

        all_mentions = await self.repo.create_many(creates)

        # Only return mentions that didn't exist before (for notifications)
        return [
            m for m in all_mentions
            if (m.mention_type, str(m.target_id)) not in existing_keys
        ]

    async def get_references(self, target_id: UUID) -> list[MentionReference]:
        """Get all places where target_id is mentioned, with source titles."""
        mentions = await self.repo.get_by_target(target_id)
        if not mentions:
            return []

        refs: list[MentionReference] = []
        for m in mentions:
            title = await self._get_source_title(m.source_type, m.source_id)
            if title:
                refs.append(
                    MentionReference(
                        source_type=m.source_type,
                        source_id=m.source_id,
                        source_title=title,
                    )
                )
        return refs

    async def _get_source_title(self, source_type: str, source_id: UUID) -> str | None:
        if source_type == "node":
            node = await self.session.get(CorpusNode, source_id)
            return node.title if node else None
        elif source_type == "task":
            task = await self.session.get(Task, source_id)
            return task.title if task else None
        elif source_type == "organisatie":
            from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid

            org = await self.session.get(OrganisatieEenheid, source_id)
            return org.naam if org else None
        elif source_type == "notification":
            from bouwmeester.models.notification import Notification

            notif = await self.session.get(Notification, source_id)
            return notif.title if notif else None
        return None

    async def search_mentionables(
        self, query: str, types: list[str] | None = None, limit: int = 10
    ) -> list[MentionSearchResult]:
        """Search across nodes, tasks, and tags for # mention suggestions."""
        results: list[MentionSearchResult] = []
        allowed = types or ["node", "task", "tag"]
        pattern = f"%{query}%"

        if "node" in allowed:
            stmt = (
                select(CorpusNode)
                .where(CorpusNode.title.ilike(pattern))
                .order_by(CorpusNode.title)
                .limit(limit)
            )
            rows = await self.session.execute(stmt)
            for n in rows.scalars().all():
                results.append(
                    MentionSearchResult(
                        id=str(n.id),
                        label=n.title,
                        type="node",
                        subtitle=n.node_type.replace("_", " "),
                    )
                )

        if "task" in allowed:
            stmt = (
                select(Task)
                .where(Task.title.ilike(pattern))
                .order_by(Task.title)
                .limit(limit)
            )
            rows = await self.session.execute(stmt)
            for t in rows.scalars().all():
                results.append(
                    MentionSearchResult(
                        id=str(t.id),
                        label=t.title,
                        type="task",
                        subtitle=t.status.replace("_", " ") if t.status else None,
                    )
                )

        if "tag" in allowed:
            from bouwmeester.models.tag import Tag

            stmt = (
                select(Tag)
                .where(Tag.name.ilike(pattern))
                .order_by(Tag.name)
                .limit(limit)
            )
            rows = await self.session.execute(stmt)
            for tag in rows.scalars().all():
                results.append(
                    MentionSearchResult(
                        id=str(tag.id),
                        label=tag.name,
                        type="tag",
                    )
                )

        # Sort combined results by label and limit
        results.sort(key=lambda r: r.label.lower())
        return results[:limit]


def _walk_tiptap(node: dict | list, mentions: list[dict]) -> None:
    """Recursively walk TipTap JSON tree and extract mention nodes."""
    if isinstance(node, list):
        for item in node:
            _walk_tiptap(item, mentions)
        return

    if not isinstance(node, dict):
        return

    node_type = node.get("type")

    if node_type == "mention":
        attrs = node.get("attrs", {})
        target_id = attrs.get("id")
        if target_id:
            mentions.append({"mention_type": "person", "target_id": str(target_id)})

    elif node_type == "hashtagMention":
        attrs = node.get("attrs", {})
        target_id = attrs.get("id")
        # mentionType is 'node', 'task', or 'tag'; default to 'node' for legacy data
        mention_type = attrs.get("mentionType", "node")
        if target_id:
            mentions.append({"mention_type": mention_type, "target_id": str(target_id)})

    # Recurse into content
    content = node.get("content")
    if content:
        _walk_tiptap(content, mentions)
