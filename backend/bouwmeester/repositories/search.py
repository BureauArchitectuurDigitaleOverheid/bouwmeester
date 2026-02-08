"""Repository for full-text search on corpus nodes."""

from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.corpus_node import CorpusNode


class SearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def full_text_search(
        self,
        query: str,
        node_types: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Search corpus nodes using PostgreSQL full-text search.

        Uses to_tsvector/to_tsquery with ts_rank on title and description.
        """
        # Build the tsvector from title (weight A) and description (weight B)
        ts_vector = func.setweight(
            func.to_tsvector("dutch", func.coalesce(CorpusNode.title, "")),
            literal_column("'A'"),
        ).op("||")(
            func.setweight(
                func.to_tsvector("dutch", func.coalesce(CorpusNode.description, "")),
                literal_column("'B'"),
            )
        )

        # Use plainto_tsquery for simpler user input handling
        ts_query = func.plainto_tsquery("dutch", query)

        rank = func.ts_rank(ts_vector, ts_query).label("rank")

        stmt = (
            select(
                CorpusNode.id,
                CorpusNode.node_type,
                CorpusNode.title,
                CorpusNode.description,
                rank,
            )
            .where(ts_vector.op("@@")(ts_query))
            .order_by(rank.desc())
            .limit(limit)
        )

        if node_types:
            stmt = stmt.where(CorpusNode.node_type.in_(node_types))

        result = await self.session.execute(stmt)
        rows = result.all()

        return [
            {
                "id": row.id,
                "node_type": row.node_type,
                "title": row.title,
                "description": row.description,
                "rank": float(row.rank),
            }
            for row in rows
        ]
