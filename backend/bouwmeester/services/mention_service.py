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
            m
            for m in all_mentions
            if (m.mention_type, str(m.target_id)) not in existing_keys
        ]

    # Only these source types should appear as public back-references.
    # DMs, org descriptions, and any future private source types are excluded.
    _PUBLIC_SOURCE_TYPES = ["node", "task"]

    async def get_references(self, target_id: UUID) -> list[MentionReference]:
        """Get all places where target_id is mentioned, with source titles.

        Only includes public source types (nodes, tasks) — private content
        like DMs and org descriptions should not leak as back-references.
        """
        mentions = await self.repo.get_by_target(
            target_id, allowed_source_types=self._PUBLIC_SOURCE_TYPES
        )
        if not mentions:
            return []

        # Batch-fetch titles by source type to avoid N+1 queries
        titles = await self._get_source_titles_batch(mentions)

        refs: list[MentionReference] = []
        for m in mentions:
            title = titles.get((m.source_type, m.source_id))
            if title:
                refs.append(
                    MentionReference(
                        source_type=m.source_type,
                        source_id=m.source_id,
                        source_title=title,
                    )
                )
        return refs

    async def _get_source_titles_batch(
        self, mentions: list[Mention]
    ) -> dict[tuple[str, UUID], str]:
        """Fetch titles for all mentions in batched IN-clause queries."""
        # Group source IDs by type
        ids_by_type: dict[str, list[UUID]] = {}
        for m in mentions:
            ids_by_type.setdefault(m.source_type, []).append(m.source_id)

        titles: dict[tuple[str, UUID], str] = {}

        if "node" in ids_by_type:
            stmt = select(CorpusNode.id, CorpusNode.title).where(
                CorpusNode.id.in_(ids_by_type["node"])
            )
            for row in (await self.session.execute(stmt)).all():
                titles[("node", row[0])] = row[1]

        if "task" in ids_by_type:
            stmt = select(Task.id, Task.title).where(
                Task.id.in_(ids_by_type["task"])
            )
            for row in (await self.session.execute(stmt)).all():
                titles[("task", row[0])] = row[1]

        return titles

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
        # mentionType attr: person vs organisatie (default "person")
        mention_type = attrs.get("mentionType", "person")
        if target_id:
            mentions.append({"mention_type": mention_type, "target_id": str(target_id)})

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
