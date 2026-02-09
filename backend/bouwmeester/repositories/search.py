"""Repository for omni full-text search across all entity types."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


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

        sub_queries = []

        if "corpus_node" in active_types:
            sub_queries.append("""
                SELECT
                    id,
                    'corpus_node' AS result_type,
                    title,
                    node_type AS subtitle,
                    description,
                    ts_rank(search_vector, plainto_tsquery('dutch', :query)) AS score
                FROM corpus_node
                WHERE search_vector @@ plainto_tsquery('dutch', :query)
            """)

        if "task" in active_types:
            sub_queries.append("""
                SELECT
                    id,
                    'task' AS result_type,
                    title,
                    status AS subtitle,
                    description,
                    ts_rank(search_vector, plainto_tsquery('dutch', :query)) AS score
                FROM task
                WHERE search_vector @@ plainto_tsquery('dutch', :query)
            """)

        if "person" in active_types:
            sub_queries.append("""
                SELECT
                    id,
                    'person' AS result_type,
                    naam AS title,
                    functie AS subtitle,
                    email AS description,
                    ts_rank(search_vector, plainto_tsquery('dutch', :query)) AS score
                FROM person
                WHERE search_vector @@ plainto_tsquery('dutch', :query)
            """)

        if "organisatie_eenheid" in active_types:
            sub_queries.append("""
                SELECT
                    id,
                    'organisatie_eenheid' AS result_type,
                    naam AS title,
                    type AS subtitle,
                    beschrijving AS description,
                    ts_rank(search_vector, plainto_tsquery('dutch', :query)) AS score
                FROM organisatie_eenheid
                WHERE search_vector @@ plainto_tsquery('dutch', :query)
            """)

        if "parlementair_item" in active_types:
            sub_queries.append("""
                SELECT
                    id,
                    'parlementair_item' AS result_type,
                    titel AS title,
                    type AS subtitle,
                    onderwerp AS description,
                    ts_rank(search_vector, plainto_tsquery('dutch', :query)) AS score
                FROM parlementair_item
                WHERE search_vector @@ plainto_tsquery('dutch', :query)
            """)

        if "tag" in active_types:
            sub_queries.append("""
                SELECT
                    id,
                    'tag' AS result_type,
                    name AS title,
                    NULL AS subtitle,
                    description,
                    ts_rank(search_vector, plainto_tsquery('dutch', :query)) AS score
                FROM tag
                WHERE search_vector @@ plainto_tsquery('dutch', :query)
            """)

        if not sub_queries:
            return []

        union_sql = " UNION ALL ".join(sub_queries)
        full_sql = f"""
            SELECT * FROM ({union_sql}) AS combined
            ORDER BY score DESC
            LIMIT :limit
        """

        result = await self.session.execute(
            text(full_sql), {"query": query, "limit": limit}
        )
        rows = result.all()

        url_map = {
            "corpus_node": "/nodes/{id}",
            "task": "/tasks?task={id}",
            "person": "/people/{id}",
            "organisatie_eenheid": "/organisatie/{id}",
            "parlementair_item": "/parlementair/{id}",
            "tag": "/corpus?tag={id}",
        }

        # Build highlights via ts_headline for the final result set
        results = []
        for row in rows:
            url = url_map[row.result_type].format(id=row.id)
            results.append(
                {
                    "id": row.id,
                    "result_type": row.result_type,
                    "title": row.title,
                    "subtitle": row.subtitle,
                    "description": row.description,
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
