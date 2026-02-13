"""Repository for omni full-text search across all entity types."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.utils.tiptap import tiptap_to_plain


class SearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def full_text_search(
        self,
        query: str,
        result_types: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Search across all entity types using stored tsvector + GIN indexes.

        Returns unified results from corpus_node, task, person,
        organisatie_eenheid, parlementair_item, and tag tables.
        """
        all_types = {
            "corpus_node",
            "task",
            "person",
            "organisatie_eenheid",
            "parlementair_item",
            "tag",
        }
        active_types = set(result_types) if result_types else all_types

        short_query = len(query.strip()) < 4

        sub_queries = []

        # title_col per entity for ILIKE fallback on short queries
        entity_title_cols = {
            "corpus_node": "title",
            "task": "title",
            "person": "naam",
            "organisatie_eenheid": "naam",
            "parlementair_item": "titel",
            "tag": "name",
        }

        def _where(title_col: str) -> str:
            fts = "search_vector @@ plainto_tsquery('dutch', :query)"
            if short_query:
                return f"({fts} OR {title_col} ILIKE :prefix)"
            return fts

        def _score(title_col: str) -> str:
            rank = "ts_rank(search_vector, plainto_tsquery('dutch', :query))"
            if short_query:
                return (
                    f"GREATEST({rank}, "
                    f"CASE WHEN {title_col} ILIKE :prefix THEN 0.1 ELSE 0 END)"
                )
            return rank

        if "corpus_node" in active_types:
            tc = entity_title_cols["corpus_node"]
            sub_queries.append(f"""
                SELECT
                    id,
                    'corpus_node' AS result_type,
                    title,
                    node_type AS subtitle,
                    description,
                    {_score(tc)} AS score
                FROM corpus_node
                WHERE {_where(tc)}
            """)

        if "task" in active_types:
            tc = entity_title_cols["task"]
            sub_queries.append(f"""
                SELECT
                    id,
                    'task' AS result_type,
                    title,
                    status AS subtitle,
                    description,
                    {_score(tc)} AS score
                FROM task
                WHERE {_where(tc)}
            """)

        if "person" in active_types:
            tc = entity_title_cols["person"]
            sub_queries.append(f"""
                SELECT
                    id,
                    'person' AS result_type,
                    naam AS title,
                    functie AS subtitle,
                    email AS description,
                    {_score(tc)} AS score
                FROM person
                WHERE {_where(tc)}
            """)

        if "organisatie_eenheid" in active_types:
            tc = entity_title_cols["organisatie_eenheid"]
            sub_queries.append(f"""
                SELECT
                    id,
                    'organisatie_eenheid' AS result_type,
                    naam AS title,
                    type AS subtitle,
                    beschrijving AS description,
                    {_score(tc)} AS score
                FROM organisatie_eenheid
                WHERE {_where(tc)}
            """)

        if "parlementair_item" in active_types:
            tc = entity_title_cols["parlementair_item"]
            sub_queries.append(f"""
                SELECT
                    id,
                    'parlementair_item' AS result_type,
                    titel AS title,
                    type AS subtitle,
                    onderwerp AS description,
                    {_score(tc)} AS score
                FROM parlementair_item
                WHERE {_where(tc)}
            """)

        if "tag" in active_types:
            tc = entity_title_cols["tag"]
            sub_queries.append(f"""
                SELECT
                    id,
                    'tag' AS result_type,
                    name AS title,
                    NULL AS subtitle,
                    description,
                    {_score(tc)} AS score
                FROM tag
                WHERE {_where(tc)}
            """)

        if not sub_queries:
            return []

        union_sql = " UNION ALL ".join(sub_queries)
        full_sql = f"""
            SELECT * FROM ({union_sql}) AS combined
            ORDER BY score DESC
            LIMIT :limit
        """

        params: dict = {"query": query, "limit": limit}
        if short_query:
            params["prefix"] = query.strip() + "%"

        result = await self.session.execute(text(full_sql), params)
        rows = result.all()

        url_map = {
            "corpus_node": "/nodes/{id}",
            "task": "/tasks?task={id}",
            "person": "/people?person={id}",
            "organisatie_eenheid": "/organisatie?eenheid={id}",
            "parlementair_item": "/parlementair?item={id}",
            "tag": "/corpus?tag={id}",
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
