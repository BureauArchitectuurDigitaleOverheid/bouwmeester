"""Repository for graph-wide queries (path-finding, full graph, community)."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.org_context import OrgContext, apply_org_filter
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge
from bouwmeester.models.externe_organisatie import ExterneOrganisatie
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_contact import LeadContact
from bouwmeester.models.lead_node import LeadNode
from bouwmeester.models.node_stakeholder import NodeStakeholder
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.repositories.graph_filters import exclude_unconnected_pi
from bouwmeester.schema.community_graph import (
    CommunityGraphEdge,
    CommunityGraphNode,
    CommunityGraphResponse,
)


class GraphRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Path finding -- shortest path via recursive CTE (BFS)
    # ------------------------------------------------------------------

    async def find_path(
        self,
        from_id: UUID,
        to_id: UUID,
        max_depth: int = 10,
    ) -> list[dict]:
        """Find the shortest path between two nodes using a recursive CTE.

        The CTE performs a breadth-first search over the ``edge`` table,
        treating edges as *undirected* (traversable in both directions).
        It returns one row per step with the full path encoded as arrays
        so we can reconstruct the route.

        Returns a list of dicts -- one per step -- each containing:
          - ``node_id``, ``node_title``, ``node_type``
          - ``edge_id``, ``edge_type_id`` (``None`` for the starting node)
        """
        query = text(
            """
            WITH RECURSIVE path_walk AS (
                -- Base: start from the source node.
                SELECT
                    cn.id        AS node_id,
                    cn.title     AS node_title,
                    cn.node_type AS node_type,
                    NULL::uuid   AS edge_id,
                    NULL::text   AS edge_type_id,
                    ARRAY[cn.id] AS visited,
                    0            AS depth
                FROM corpus_node cn
                WHERE cn.id = :from_id

                UNION ALL

                -- Recursive: follow edges in both directions.
                SELECT
                    next_node.id,
                    next_node.title,
                    next_node.node_type,
                    e.id,
                    e.edge_type_id,
                    pw.visited || next_node.id,
                    pw.depth + 1
                FROM path_walk pw
                JOIN edge e
                    ON (e.from_node_id = pw.node_id OR e.to_node_id = pw.node_id)
                JOIN corpus_node next_node
                    ON next_node.id = CASE
                        WHEN e.from_node_id = pw.node_id THEN e.to_node_id
                        ELSE e.from_node_id
                    END
                WHERE pw.depth < :max_depth
                  AND NOT (next_node.id = ANY(pw.visited))
            )
            SELECT
                node_id,
                node_title,
                node_type,
                edge_id,
                edge_type_id,
                visited,
                depth
            FROM path_walk
            WHERE node_id = :to_id
            ORDER BY depth
            LIMIT 1
            """
        )

        result = await self.session.execute(
            query,
            {
                "from_id": str(from_id),
                "to_id": str(to_id),
                "max_depth": max_depth,
            },
        )
        row = result.first()

        if row is None:
            return []

        # ``visited`` contains the ordered list of node IDs from source to
        # target.  We now reconstruct the full path with node + edge info.
        visited_ids: list[UUID] = list(row.visited)

        # Fetch all nodes on the path.
        nodes_stmt = select(CorpusNode).where(CorpusNode.id.in_(visited_ids))
        nodes_result = await self.session.execute(nodes_stmt)
        node_map = {n.id: n for n in nodes_result.scalars().all()}

        # Fetch all edges between consecutive nodes on the path.
        path_steps: list[dict] = []
        for i, nid in enumerate(visited_ids):
            node = node_map.get(nid)
            step: dict = {
                "node_id": nid,
                "node_title": node.title if node else None,
                "node_type": node.node_type if node else None,
                "edge_id": None,
                "edge_type_id": None,
            }
            if i > 0:
                prev_id = visited_ids[i - 1]
                edge_stmt = select(Edge).where(
                    ((Edge.from_node_id == prev_id) & (Edge.to_node_id == nid))
                    | ((Edge.from_node_id == nid) & (Edge.to_node_id == prev_id))
                )
                edge_result = await self.session.execute(edge_stmt)
                edge = edge_result.scalar_one_or_none()
                if edge:
                    step["edge_id"] = edge.id
                    step["edge_type_id"] = edge.edge_type_id
            path_steps.append(step)

        return path_steps

    # ------------------------------------------------------------------
    # Full graph -- all nodes and edges, optionally filtered
    # ------------------------------------------------------------------

    async def get_full_graph(
        self,
        node_types: list[str] | None = None,
        edge_types: list[str] | None = None,
        org_ctx: OrgContext | None = None,
    ) -> dict:
        """Return all nodes and edges, optionally filtered by type.

        By default, politieke_input nodes are only included when they have
        at least one edge (i.e. they are connected to the policy graph).

        Returns ``{"nodes": [...], "edges": [...]}``.
        """
        # -- Nodes --
        nodes_stmt = select(CorpusNode)
        if node_types:
            nodes_stmt = nodes_stmt.where(CorpusNode.node_type.in_(node_types))

        # Exclude unconnected politieke_input at the SQL level.
        if not node_types or "politieke_input" in node_types:
            nodes_stmt = nodes_stmt.where(exclude_unconnected_pi())

        nodes_stmt = apply_org_filter(
            nodes_stmt, CorpusNode.organisatie_eenheid_id, org_ctx
        )
        nodes_stmt = nodes_stmt.order_by(CorpusNode.created_at.desc())
        nodes_result = await self.session.execute(nodes_stmt)
        nodes = list(nodes_result.scalars().all())

        node_ids = {n.id for n in nodes}

        # -- Edges --
        edges_stmt = select(Edge)
        if edge_types:
            edges_stmt = edges_stmt.where(Edge.edge_type_id.in_(edge_types))
        # Only include edges whose *both* endpoints are in the visible node set.
        # When org filtering is active, node_ids already reflects visibility,
        # so edges between invisible nodes are automatically excluded.
        if node_types or org_ctx is not None:
            edges_stmt = edges_stmt.where(
                Edge.from_node_id.in_(node_ids),
                Edge.to_node_id.in_(node_ids),
            )
        edges_result = await self.session.execute(edges_stmt)
        edges = list(edges_result.scalars().all())

        return {"nodes": nodes, "edges": edges}

    # ------------------------------------------------------------------
    # Community graph -- leads, people, orgs, corpus nodes and relations
    # ------------------------------------------------------------------

    async def get_community_graph(
        self,
        org_ctx: OrgContext | None = None,
    ) -> CommunityGraphResponse:
        """Build a unified graph of leads, persons, organisations and corpus nodes.

        The graph includes all visible leads (filtered by OrgContext) and
        transitively collects every person, external organisation, internal
        organisatie-eenheid, and corpus node connected to those leads.

        Returns a ``CommunityGraphResponse`` with deduplicated nodes and edges.
        """
        graph_nodes: dict[str, CommunityGraphNode] = {}
        graph_edges: list[CommunityGraphEdge] = []
        edge_counter = 0

        def _next_edge_id() -> str:
            nonlocal edge_counter
            edge_counter += 1
            return f"ce-{edge_counter}"

        # -- 1. Visible leads --
        leads_stmt = select(Lead)
        leads_stmt = apply_org_filter(leads_stmt, Lead.organisatie_eenheid_id, org_ctx)
        leads_result = await self.session.execute(leads_stmt)
        leads = list(leads_result.scalars().all())

        lead_ids = set[UUID]()
        for lead in leads:
            lid = f"lead-{lead.id}"
            lead_ids.add(lead.id)
            graph_nodes[lid] = CommunityGraphNode(
                id=lid,
                node_type="lead",
                label=lead.title,
                stage=lead.stage,
            )

        if not lead_ids:
            return CommunityGraphResponse(nodes=[], edges=[])

        # -- 2. Lead → ExterneOrganisatie edges --
        ext_org_ids = {
            lead.externe_organisatie_id
            for lead in leads
            if lead.externe_organisatie_id is not None
        }
        if ext_org_ids:
            ext_orgs_stmt = select(ExterneOrganisatie).where(
                ExterneOrganisatie.id.in_(ext_org_ids)
            )
            ext_orgs_result = await self.session.execute(ext_orgs_stmt)
            for ext_org in ext_orgs_result.scalars().all():
                oid = f"org-{ext_org.id}"
                graph_nodes[oid] = CommunityGraphNode(
                    id=oid,
                    node_type="organisation",
                    label=ext_org.naam,
                    org_type=ext_org.type,
                )

            for lead in leads:
                if lead.externe_organisatie_id is not None:
                    graph_edges.append(
                        CommunityGraphEdge(
                            id=_next_edge_id(),
                            source=f"lead-{lead.id}",
                            target=f"org-{lead.externe_organisatie_id}",
                            edge_type="organisatie",
                            label="externe organisatie",
                        )
                    )

        # -- 3. Lead → Person (assignee) edges --
        person_ids = set[UUID]()
        for lead in leads:
            if lead.assignee_id is not None:
                person_ids.add(lead.assignee_id)
                graph_edges.append(
                    CommunityGraphEdge(
                        id=_next_edge_id(),
                        source=f"lead-{lead.id}",
                        target=f"person-{lead.assignee_id}",
                        edge_type="verantwoordelijke",
                        label="verantwoordelijke",
                    )
                )

        # -- 4. Lead → Person (contacts via LeadContact) --
        contacts_stmt = select(LeadContact).where(LeadContact.lead_id.in_(lead_ids))
        contacts_result = await self.session.execute(contacts_stmt)
        for contact in contacts_result.scalars().all():
            person_ids.add(contact.person_id)
            graph_edges.append(
                CommunityGraphEdge(
                    id=_next_edge_id(),
                    source=f"lead-{contact.lead_id}",
                    target=f"person-{contact.person_id}",
                    edge_type="contact",
                    label=contact.rol,
                )
            )

        # -- 5. Lead → CorpusNode (via LeadNode) --
        lead_nodes_stmt = select(LeadNode).where(LeadNode.lead_id.in_(lead_ids))
        lead_nodes_result = await self.session.execute(lead_nodes_stmt)
        lead_node_rows = list(lead_nodes_result.scalars().all())

        corpus_node_ids = {ln.node_id for ln in lead_node_rows}
        for ln in lead_node_rows:
            graph_edges.append(
                CommunityGraphEdge(
                    id=_next_edge_id(),
                    source=f"lead-{ln.lead_id}",
                    target=f"node-{ln.node_id}",
                    edge_type="gelinkt",
                    label="gelinkt dossieronderdeel",
                )
            )

        # Fetch the actual corpus nodes (apply org filter)
        if corpus_node_ids:
            cn_stmt = select(CorpusNode).where(CorpusNode.id.in_(corpus_node_ids))
            cn_stmt = apply_org_filter(
                cn_stmt, CorpusNode.organisatie_eenheid_id, org_ctx
            )
            cn_result = await self.session.execute(cn_stmt)
            visible_corpus_nodes = list(cn_result.scalars().all())
            visible_cn_ids = set[UUID]()
            for cn in visible_corpus_nodes:
                nid = f"node-{cn.id}"
                visible_cn_ids.add(cn.id)
                graph_nodes[nid] = CommunityGraphNode(
                    id=nid,
                    node_type="corpus_node",
                    label=cn.title,
                    corpus_node_type=cn.node_type,
                )
            # Remove edges to invisible corpus nodes
            graph_edges = [
                e
                for e in graph_edges
                if not (
                    e.target.startswith("node-")
                    and UUID(e.target.removeprefix("node-")) not in visible_cn_ids
                )
            ]
            corpus_node_ids = visible_cn_ids
        else:
            visible_corpus_nodes = []

        # -- 6. CorpusNode → CorpusNode (via Edge table) --
        if corpus_node_ids:
            corpus_edges_stmt = select(Edge).where(
                or_(
                    Edge.from_node_id.in_(corpus_node_ids),
                    Edge.to_node_id.in_(corpus_node_ids),
                )
            )
            corpus_edges_result = await self.session.execute(corpus_edges_stmt)
            for edge in corpus_edges_result.scalars().all():
                # Only include edges where both endpoints are in our set
                if (
                    edge.from_node_id in corpus_node_ids
                    and edge.to_node_id in corpus_node_ids
                ):
                    graph_edges.append(
                        CommunityGraphEdge(
                            id=f"edge-{edge.id}",
                            source=f"node-{edge.from_node_id}",
                            target=f"node-{edge.to_node_id}",
                            edge_type=edge.edge_type_id,
                            label=edge.edge_type_id,
                        )
                    )

        # -- 7. CorpusNode → Person (via NodeStakeholder) --
        if corpus_node_ids:
            stakeholders_stmt = select(NodeStakeholder).where(
                NodeStakeholder.node_id.in_(corpus_node_ids)
            )
            stakeholders_result = await self.session.execute(stakeholders_stmt)
            for sh in stakeholders_result.scalars().all():
                person_ids.add(sh.person_id)
                graph_edges.append(
                    CommunityGraphEdge(
                        id=_next_edge_id(),
                        source=f"node-{sh.node_id}",
                        target=f"person-{sh.person_id}",
                        edge_type=sh.rol,
                        label=sh.rol,
                    )
                )

        # -- 8. Fetch all collected persons --
        if person_ids:
            persons_stmt = select(Person).where(Person.id.in_(person_ids))
            persons_result = await self.session.execute(persons_stmt)
            for person in persons_result.scalars().all():
                pid = f"person-{person.id}"
                graph_nodes[pid] = CommunityGraphNode(
                    id=pid,
                    node_type="person",
                    label=person.naam,
                    functie=person.functie,
                )

        # -- 9. Person → OrganisatieEenheid (active plaatsingen) --
        if person_ids:
            today = date.today()
            plaatsingen_stmt = select(PersonOrganisatieEenheid).where(
                PersonOrganisatieEenheid.person_id.in_(person_ids),
                PersonOrganisatieEenheid.start_datum <= today,
                or_(
                    PersonOrganisatieEenheid.eind_datum.is_(None),
                    PersonOrganisatieEenheid.eind_datum >= today,
                ),
            )
            plaatsingen_result = await self.session.execute(plaatsingen_stmt)
            oe_ids = set[UUID]()
            plaatsing_rows = list(plaatsingen_result.scalars().all())
            for pl in plaatsing_rows:
                oe_ids.add(pl.organisatie_eenheid_id)

            if oe_ids:
                oe_stmt = select(OrganisatieEenheid).where(
                    OrganisatieEenheid.id.in_(oe_ids)
                )
                oe_result = await self.session.execute(oe_stmt)
                for oe in oe_result.scalars().all():
                    oe_key = f"oe-{oe.id}"
                    graph_nodes[oe_key] = CommunityGraphNode(
                        id=oe_key,
                        node_type="organisation",
                        label=oe.naam,
                        org_type=oe.type,
                    )

                for pl in plaatsing_rows:
                    graph_edges.append(
                        CommunityGraphEdge(
                            id=_next_edge_id(),
                            source=f"person-{pl.person_id}",
                            target=f"oe-{pl.organisatie_eenheid_id}",
                            edge_type="lid_van",
                            label="lid van",
                        )
                    )

        return CommunityGraphResponse(
            nodes=list(graph_nodes.values()),
            edges=graph_edges,
        )
