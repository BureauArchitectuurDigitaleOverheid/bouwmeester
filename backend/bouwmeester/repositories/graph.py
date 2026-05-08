"""Repository for graph-wide queries (path-finding, full graph, community)."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.initiatief_context import (
    InitiatiefContext,
    apply_initiatief_filter,
)
from bouwmeester.core.org_context import OrgContext, apply_org_filter
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge
from bouwmeester.models.externe_organisatie import ExterneOrganisatie
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_node import LeadNode
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.persoon_samenwerkingsverband import (
    PersoonSamenwerkingsverband,
)
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.samenwerkingsverband import Samenwerkingsverband
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
        init_ctx: InitiatiefContext | None = None,
        initiatief_id: UUID | None = None,
    ) -> CommunityGraphResponse:
        """Build a unified graph of leads, persons, organisations and corpus nodes.

        The graph starts from leads filtered by ``init_ctx`` (visibility) and,
        when ``initiatief_id`` is given, narrowed to that single initiatief.
        It then transitively collects every person, external organisation,
        samenwerkingsverband and corpus node connected to those leads.

        Returns a ``CommunityGraphResponse`` with deduplicated nodes and edges.
        """
        graph_nodes: dict[str, CommunityGraphNode] = {}
        graph_edges: list[CommunityGraphEdge] = []
        # Org keys (graph_nodes IDs) where at least one internal person is
        # actively placed. Used at the end to flag org_role="intern" so the
        # frontend can put these in a separate swim-lane.
        internal_org_keys: set[str] = set()
        edge_counter = 0

        def _next_edge_id() -> str:
            nonlocal edge_counter
            edge_counter += 1
            return f"ce-{edge_counter}"

        # -- 1. Visible leads --
        leads_stmt = select(Lead)
        leads_stmt = apply_initiatief_filter(leads_stmt, Lead.initiatief_id, init_ctx)
        if initiatief_id is not None:
            leads_stmt = leads_stmt.where(Lead.initiatief_id == initiatief_id)
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
                initiatief_id=str(lead.initiatief_id) if lead.initiatief_id else None,
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

        # -- 2b. Lead → organisation (free-text field) --
        for lead in leads:
            if lead.organization and not lead.externe_organisatie_id:
                org_key = f"orgtext-{lead.organization}"
                if org_key not in graph_nodes:
                    graph_nodes[org_key] = CommunityGraphNode(
                        id=org_key,
                        node_type="organisation",
                        label=lead.organization,
                    )
                graph_edges.append(
                    CommunityGraphEdge(
                        id=_next_edge_id(),
                        source=f"lead-{lead.id}",
                        target=org_key,
                        edge_type="organisatie",
                        label="organisatie",
                    )
                )

        # -- 3. Lead → Person (assignee) edges --
        # Track internal vs external persons for visual distinction in the graph.
        # Internal = assignee or corpus-stakeholder. External = only reachable
        # through a lead-contact ResourcePermission. brought_by_id is intentionally
        # not added here: there is no edge for it, so adding the person would yield
        # a disconnected node.
        person_ids = set[UUID]()
        internal_person_ids = set[UUID]()
        external_person_ids = set[UUID]()
        for lead in leads:
            if lead.assignee_id is not None:
                person_ids.add(lead.assignee_id)
                internal_person_ids.add(lead.assignee_id)
                graph_edges.append(
                    CommunityGraphEdge(
                        id=_next_edge_id(),
                        source=f"lead-{lead.id}",
                        target=f"person-{lead.assignee_id}",
                        edge_type="verantwoordelijke",
                        label="verantwoordelijke",
                    )
                )

        # -- 4. Lead → Person (contacts via ResourcePermission) --
        # Map the database-level rol values to user-facing labels. The DB still
        # stores "contactpersoon"; the UI renames it to "externe contactpersoon".
        contact_label_map = {
            "contactpersoon": "externe contactpersoon",
            "opdrachtgever": "opdrachtgever",
            "betrokken": "betrokken",
        }
        contacts_stmt = select(ResourcePermission).where(
            ResourcePermission.resource_type == "lead",
            ResourcePermission.resource_id.in_(lead_ids),
        )
        contacts_result = await self.session.execute(contacts_stmt)
        for contact in contacts_result.scalars().all():
            person_ids.add(contact.person_id)
            external_person_ids.add(contact.person_id)
            graph_edges.append(
                CommunityGraphEdge(
                    id=_next_edge_id(),
                    source=f"lead-{contact.resource_id}",
                    target=f"person-{contact.person_id}",
                    edge_type="contact",
                    label=contact_label_map.get(contact.rol, contact.rol),
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

        # -- 7. CorpusNode → Person (via ResourcePermission) --
        if corpus_node_ids:
            stakeholders_stmt = select(ResourcePermission).where(
                ResourcePermission.resource_type == "corpus_node",
                ResourcePermission.resource_id.in_(corpus_node_ids),
            )
            stakeholders_result = await self.session.execute(stakeholders_stmt)
            for sh in stakeholders_result.scalars().all():
                person_ids.add(sh.person_id)
                internal_person_ids.add(sh.person_id)
                graph_edges.append(
                    CommunityGraphEdge(
                        id=_next_edge_id(),
                        source=f"node-{sh.resource_id}",
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
                # Intern wins over extern when a person is both
                if person.id in internal_person_ids:
                    role = "intern"
                elif person.id in external_person_ids:
                    role = "extern"
                else:
                    role = None
                graph_nodes[pid] = CommunityGraphNode(
                    id=pid,
                    node_type="person",
                    label=person.naam,
                    functie=person.functie,
                    expertise=person.expertise,
                    person_role=role,
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
                    oe_key = f"oe-{pl.organisatie_eenheid_id}"
                    if pl.person_id in internal_person_ids:
                        internal_org_keys.add(oe_key)
                    graph_edges.append(
                        CommunityGraphEdge(
                            id=_next_edge_id(),
                            source=f"person-{pl.person_id}",
                            target=oe_key,
                            edge_type="lid_van",
                            label="lid van",
                        )
                    )

        # -- 10. Person → Samenwerkingsverband (active lidmaatschappen) --
        if person_ids:
            today = date.today()
            swv_lid_stmt = select(PersoonSamenwerkingsverband).where(
                PersoonSamenwerkingsverband.person_id.in_(person_ids),
                PersoonSamenwerkingsverband.start_datum <= today,
                or_(
                    PersoonSamenwerkingsverband.eind_datum.is_(None),
                    PersoonSamenwerkingsverband.eind_datum >= today,
                ),
            )
            swv_lid_result = await self.session.execute(swv_lid_stmt)
            swv_lid_rows = list(swv_lid_result.scalars().all())
            swv_ids = {lid.samenwerkingsverband_id for lid in swv_lid_rows}

            if swv_ids:
                swv_stmt = select(Samenwerkingsverband).where(
                    Samenwerkingsverband.id.in_(swv_ids)
                )
                swv_result = await self.session.execute(swv_stmt)
                for swv in swv_result.scalars().all():
                    swv_key = f"swv-{swv.id}"
                    graph_nodes[swv_key] = CommunityGraphNode(
                        id=swv_key,
                        node_type="samenwerkingsverband",
                        label=swv.naam,
                        samenwerkingsverband_type=swv.type,
                    )

                for lid in swv_lid_rows:
                    graph_edges.append(
                        CommunityGraphEdge(
                            id=_next_edge_id(),
                            source=f"person-{lid.person_id}",
                            target=f"swv-{lid.samenwerkingsverband_id}",
                            edge_type="lid_van_swv",
                            label=lid.rol or "lid",
                        )
                    )

        for node in graph_nodes.values():
            if node.node_type == "organisation":
                node.org_role = "intern" if node.id in internal_org_keys else "extern"

        return CommunityGraphResponse(
            nodes=list(graph_nodes.values()),
            edges=graph_edges,
        )
