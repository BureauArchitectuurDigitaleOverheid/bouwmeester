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
        max_nodes: int = 1000,
    ) -> list[UUID]:
        """Collect instrument node IDs reachable from the given node.

        For instrument nodes, returns [node_id] directly.
        For other nodes, uses iterative BFS with a visited set to traverse
        edges and find connected instruments, preventing cycles.
        Stops early if the visited set exceeds max_nodes to prevent
        runaway traversal on pathologically wide graphs.
        """
        if node_type == "instrument":
            return [node_id]

        visited: set[UUID] = set()
        frontier: set[UUID] = {node_id}

        for _ in range(max_depth):
            if not frontier:
                break
            visited.update(frontier)
            if len(visited) > max_nodes:
                break

            # Forward edges
            fwd_stmt = (
                select(Edge.to_node_id)
                .where(Edge.from_node_id.in_(frontier))
                .where(Edge.to_node_id.notin_(visited))
            )
            # Reverse edges
            rev_stmt = (
                select(Edge.from_node_id)
                .where(Edge.to_node_id.in_(frontier))
                .where(Edge.from_node_id.notin_(visited))
            )
            combined = fwd_stmt.union(rev_stmt)
            result = await self.session.execute(combined)
            frontier = set(result.scalars().all())

        # From all reachable nodes, pick instruments
        all_reachable = visited | frontier
        all_reachable.discard(node_id)
        if not all_reachable:
            return []

        stmt = (
            select(CorpusNode.id)
            .where(CorpusNode.id.in_(all_reachable))
            .where(CorpusNode.node_type == "instrument")
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
