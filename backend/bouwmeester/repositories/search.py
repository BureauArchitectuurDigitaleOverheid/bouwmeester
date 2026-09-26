"""Repository for omni full-text search across all entity types."""

from __future__ import annotations

from sqlalchemy import (
    String,
    case,
    func,
    literal,
    literal_column,
    null,
    select,
    text,
    union_all,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.initiatief_context import InitiatiefContext, apply_lead_filter
from bouwmeester.core.org_context import (
    OrgContext,
    apply_node_filter,
    apply_task_filter,
)
from bouwmeester.core.query_utils import escape_like
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.lead import Lead
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.parlementair_item import ParlementairItem
from bouwmeester.models.person import Person
from bouwmeester.models.tag import Tag
from bouwmeester.models.task import Task
from bouwmeester.utils.tiptap import tiptap_to_plain

# Per result type: the model and its (title, subtitle, description) columns.
# Visibility is applied per type with the same filters as the list routes;
# people, eenheden, parlementaire items and tags are tenant-wide (the route
# gates those types on their permission).
_ENTITIES = {
    "corpus_node": (
        CorpusNode,
        lambda: (CorpusNode.title, CorpusNode.node_type, CorpusNode.description),
    ),
    "task": (Task, lambda: (Task.title, Task.status, Task.description)),
    "person": (Person, lambda: (Person.naam, Person.functie, Person.email)),
    "organisatie_eenheid": (
        OrganisatieEenheid,
        lambda: (
            OrganisatieEenheid.naam,
            OrganisatieEenheid.type,
            OrganisatieEenheid.beschrijving,
        ),
    ),
    "parlementair_item": (
        ParlementairItem,
        lambda: (
            ParlementairItem.titel,
            ParlementairItem.type,
            ParlementairItem.onderwerp,
        ),
    ),
    "tag": (Tag, lambda: (Tag.name, null(), Tag.description)),
    "lead": (Lead, lambda: (Lead.title, Lead.stage, Lead.description)),
}


class SearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def full_text_search(
        self,
        query: str,
        result_types: list[str] | None = None,
        limit: int = 50,
        org_ctx: OrgContext | None = None,
        init_ctx: InitiatiefContext | None = None,
    ) -> list[dict]:
        """Search across all entity types using stored tsvector + GIN indexes.

        Each type is matched on its ``search_vector`` (stemmed words) or on
        a substring of its title (abbreviations like "JenV" inside
        "MinJenV"), and restricted to what the caller sees: nodes, tasks
        and leads through the same filters as their list routes.
        """
        active_types = [
            t for t in _ENTITIES if result_types is None or t in result_types
        ]
        tsquery = func.plainto_tsquery("dutch", query)
        pattern = f"%{escape_like(query.strip())}%"
        visibility = {
            "corpus_node": lambda stmt: apply_node_filter(stmt, org_ctx),
            "task": lambda stmt: apply_task_filter(stmt, org_ctx),
            "lead": lambda stmt: apply_lead_filter(stmt, init_ctx),
        }

        sub_queries = []
        for result_type in active_types:
            model, columns = _ENTITIES[result_type]
            title, subtitle, description = columns()
            vector = literal_column(f"{model.__tablename__}.search_vector")
            rank = func.ts_rank(vector, tsquery)
            title_match = title.ilike(pattern)
            stmt = (
                select(
                    model.id.label("id"),
                    literal(result_type, String).label("result_type"),
                    title.label("title"),
                    subtitle.label("subtitle"),
                    description.label("description"),
                    func.greatest(rank, case((title_match, 0.05), else_=0.0)).label(
                        "score"
                    ),
                )
                .select_from(model)
                .where(vector.op("@@")(tsquery) | title_match)
            )
            restrict = visibility.get(result_type)
            sub_queries.append(restrict(stmt) if restrict else stmt)

        if not sub_queries:
            return []

        combined = union_all(*sub_queries).subquery("combined")
        full = select(combined).order_by(combined.c.score.desc()).limit(limit)
        rows = (await self.session.execute(full)).all()

        url_map = {
            "corpus_node": "/nodes/{id}",
            "task": "/tasks?task={id}",
            "person": "/people?person={id}",
            "organisatie_eenheid": "/organisatie?eenheid={id}",
            "parlementair_item": "/parlementair?item={id}",
            "tag": "/corpus?tag={id}",
            "lead": "/leads?lead={id}",
        }

        # Build results, converting TipTap JSON descriptions to plain text
        results = []
        for row in rows:
            url = url_map[row.result_type].format(id=row.id)
            description = tiptap_to_plain(row.description)
            results.append(
                {
                    "id": row.id,
                    "result_type": row.result_type,
                    "title": row.title,
                    "subtitle": row.subtitle,
                    "description": description,
                    "score": float(row.score),
                    "highlights": None,
                    "url": url,
                }
            )

        # Generate highlights for rows that have descriptions
        if results:
            ids_with_desc = [(i, r) for i, r in enumerate(results) if r["description"]]
            if ids_with_desc:
                await self._add_highlights(ids_with_desc, query)

        return results

    async def find_similar_nodes(
        self,
        title: str,
        description: str | None = None,
        exclude_node_id: str | None = None,
        limit: int = 5,
        org_ctx: OrgContext | None = None,
    ) -> list[dict]:
        """Find nodes with similar titles using trigram similarity + FTS.

        Returns a list of dicts with id, title, node_type, similarity score.
        Requires the pg_trgm extension.
        """
        tsquery = func.plainto_tsquery("dutch", title)
        vector = literal_column("corpus_node.search_vector")
        trigram = func.similarity(CorpusNode.title, title)
        fts = case((vector.op("@@")(tsquery), func.ts_rank(vector, tsquery)), else_=0.0)
        # Composite score: trigram similarity on title + FTS on the vector.
        combined_score = (trigram * 0.7 + fts * 0.3).label("combined_score")
        stmt = select(
            CorpusNode.id, CorpusNode.title, CorpusNode.node_type, combined_score
        ).where(trigram > 0.15)
        if exclude_node_id:
            stmt = stmt.where(CorpusNode.id != exclude_node_id)
        stmt = apply_node_filter(stmt, org_ctx)
        stmt = stmt.order_by(combined_score.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).all()

        return [
            {
                "id": row.id,
                "title": row.title,
                "node_type": row.node_type,
                "similarity": round(float(row.combined_score), 3),
            }
            for row in rows
            if row.combined_score > 0.15
        ]

    async def _add_highlights(
        self, indexed_results: list[tuple[int, dict]], query: str
    ) -> None:
        """Add ts_headline highlights to results that have descriptions."""
        for _idx, result in indexed_results:
            desc = result["description"] or ""
            if not desc:
                continue
            hl_result = await self.session.execute(
                text("""
                    SELECT ts_headline(
                        'dutch',
                        :desc,
                        plainto_tsquery('dutch', :query),
                        'StartSel=<mark>,StopSel=</mark>,MaxWords=35,MinWords=15,MaxFragments=2'
                    ) AS headline
                """),
                {"desc": desc, "query": query},
            )
            headline = hl_result.scalar()
            if headline and "<mark>" in headline:
                result["highlights"] = [headline]
