"""Service for financial aggregation across the policy graph.

Aggregates budget/gerealiseerd data from Opdrachten, following graph edges
to collect financial data for instruments, maatregelen, doelen, etc.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge
from bouwmeester.models.opdracht import Opdracht, OpdrachtNode
from bouwmeester.schema.opdracht import FinancieelJaar, FinancieelOverzicht


class FinancieelService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_financieel_overzicht(self, node_id: UUID) -> FinancieelOverzicht:
        """Get financial overview for a node.

        For instrument nodes: aggregate directly linked opdrachten.
        For other nodes: follow edges to find connected instruments, then aggregate.
        Deduplicates opdrachten when multiple paths lead to the same one.
        """
        node = await self.session.get(CorpusNode, node_id)
        if node is None:
            return FinancieelOverzicht(
                node_id=node_id,
                node_title="",
                node_type="",
            )

        instrument_ids = await self._collect_instrument_ids(node_id, node.node_type)

        if not instrument_ids:
            return FinancieelOverzicht(
                node_id=node_id,
                node_title=node.title,
                node_type=node.node_type,
            )

        # Also include opdrachten linked via OpdrachtNode junction
        direct_stmt = select(Opdracht.id).where(
            Opdracht.instrument_id.in_(instrument_ids)
        )
        junction_stmt = select(OpdrachtNode.opdracht_id).where(
            OpdrachtNode.node_id == node_id
        )
        all_opdracht_ids = direct_stmt.union(junction_stmt).subquery()

        stmt = (
            select(
                Opdracht.begrotingsjaar,
                func.coalesce(func.sum(Opdracht.budget), 0).label("budget"),
                func.coalesce(func.sum(Opdracht.gerealiseerd), 0).label("gerealiseerd"),
                func.coalesce(func.sum(Opdracht.volgend_jaar_benodigd), 0).label(
                    "volgend_jaar_benodigd"
                ),
                func.coalesce(func.sum(Opdracht.volgend_jaar_aangevraagd), 0).label(
                    "volgend_jaar_aangevraagd"
                ),
                func.count(Opdracht.id).label("opdracht_count"),
            )
            .where(Opdracht.id.in_(select(all_opdracht_ids.c.id)))
            .group_by(Opdracht.begrotingsjaar)
            .order_by(Opdracht.begrotingsjaar)
        )

        result = await self.session.execute(stmt)
        per_jaar = [
            FinancieelJaar(
                begrotingsjaar=row.begrotingsjaar,
                budget=row.budget,
                gerealiseerd=row.gerealiseerd,
                volgend_jaar_benodigd=row.volgend_jaar_benodigd,
                volgend_jaar_aangevraagd=row.volgend_jaar_aangevraagd,
                opdracht_count=row.opdracht_count,
            )
            for row in result.all()
        ]

        totaal_budget = sum(j.budget for j in per_jaar)
        totaal_gerealiseerd = sum(j.gerealiseerd for j in per_jaar)
        uitnutting = None
        if totaal_budget and totaal_budget > 0:
            uitnutting = float(totaal_gerealiseerd / totaal_budget * 100)

        return FinancieelOverzicht(
            node_id=node_id,
            node_title=node.title,
            node_type=node.node_type,
            totaal_budget=totaal_budget,
            totaal_gerealiseerd=totaal_gerealiseerd,
            uitnutting_percentage=uitnutting,
            per_jaar=per_jaar,
        )

    async def _collect_instrument_ids(
        self,
        node_id: UUID,
        node_type: str,
        max_depth: int = 5,
    ) -> list[UUID]:
        """Collect instrument node IDs reachable from the given node.

        For instrument nodes, returns [node_id] directly.
        For other nodes, uses a bounded BFS via recursive CTE to traverse edges
        and find connected instruments, using UNION to prevent cycles.
        """
        if node_type == "instrument":
            return [node_id]

        from sqlalchemy import literal_column

        # Recursive CTE with depth tracking and UNION (not UNION ALL) to break cycles
        cte = (
            select(
                Edge.to_node_id.label("id"),
                literal_column("1").label("depth"),
            )
            .where(Edge.from_node_id == node_id)
            .cte(name="reachable", recursive=True)
        )
        cte = cte.union(
            select(Edge.to_node_id, (cte.c.depth + 1).label("depth"))
            .join(cte, Edge.from_node_id == cte.c.id)
            .where(cte.c.depth < max_depth)
        )

        # Also traverse reverse edges with the same protections
        cte_rev = (
            select(
                Edge.from_node_id.label("id"),
                literal_column("1").label("depth"),
            )
            .where(Edge.to_node_id == node_id)
            .cte(name="reachable_rev", recursive=True)
        )
        cte_rev = cte_rev.union(
            select(Edge.from_node_id, (cte_rev.c.depth + 1).label("depth"))
            .join(cte_rev, Edge.to_node_id == cte_rev.c.id)
            .where(cte_rev.c.depth < max_depth)
        )

        # Combine forward and reverse reachable, filter for instruments
        forward_instruments = (
            select(CorpusNode.id)
            .where(CorpusNode.id.in_(select(cte.c.id)))
            .where(CorpusNode.node_type == "instrument")
        )
        reverse_instruments = (
            select(CorpusNode.id)
            .where(CorpusNode.id.in_(select(cte_rev.c.id)))
            .where(CorpusNode.node_type == "instrument")
        )
        combined = forward_instruments.union(reverse_instruments)

        result = await self.session.execute(combined)
        return list(result.scalars().all())
