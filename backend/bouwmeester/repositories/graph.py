"""Repository for graph-wide queries (path-finding, full graph, community).

Every corpus query here takes the caller's ``OrgContext``: a node the caller
does not see is left out, and so is every edge with an invisible end.
Walks (neighbours, subgraphs, paths) only step through visible nodes, so an
invisible node never shows up as a bridge between two visible ones.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from bouwmeester.core.initiatief_context import (
    InitiatiefContext,
    apply_lead_filter,
)
from bouwmeester.core.org_context import OrgContext, apply_org_filter
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge
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


def _other_end(edge: Edge, node_id: UUID) -> UUID:
    return edge.to_node_id if edge.from_node_id == node_id else edge.from_node_id


class GraphRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Visibility building blocks
    # ------------------------------------------------------------------

    async def _visible_nodes(
        self, node_ids: set[UUID], org_ctx: OrgContext
    ) -> dict[UUID, CorpusNode]:
        """The nodes among *node_ids* the caller sees, by id."""
        if not node_ids:
            return {}
        stmt = apply_org_filter(
            select(CorpusNode).where(CorpusNode.id.in_(node_ids)),
            CorpusNode.organisatie_eenheid_id,
            org_ctx,
        )
        return {n.id: n for n in (await self.session.scalars(stmt)).all()}

    async def _visible_edges_touching(
        self, node_ids: set[UUID], org_ctx: OrgContext
    ) -> list[Edge]:
        """Edges with an end in *node_ids* whose both ends the caller sees."""
        if not node_ids:
            return []
        src = aliased(CorpusNode)
        dst = aliased(CorpusNode)
        stmt = (
            select(Edge)
            .join(src, Edge.from_node_id == src.id)
            .join(dst, Edge.to_node_id == dst.id)
            .where(or_(Edge.from_node_id.in_(node_ids), Edge.to_node_id.in_(node_ids)))
            .order_by(Edge.created_at, Edge.id)
        )
        stmt = apply_org_filter(stmt, src.organisatie_eenheid_id, org_ctx)
        stmt = apply_org_filter(stmt, dst.organisatie_eenheid_id, org_ctx)
        return list((await self.session.scalars(stmt)).all())

    # ------------------------------------------------------------------
    # Neighbours and subgraph around one node
    # ------------------------------------------------------------------

    async def get_neighbors(self, node_id: UUID, *, org_ctx: OrgContext) -> dict:
        """The node and its visible direct neighbours with the connecting edges.

        ``{"node": None, ...}`` when the node does not exist or is invisible.
        """
        node = (await self._visible_nodes({node_id}, org_ctx)).get(node_id)
        if node is None:
            return {"node": None, "neighbors": []}
        edges = await self._visible_edges_touching({node_id}, org_ctx)
        others = await self._visible_nodes(
            {_other_end(e, node_id) for e in edges}, org_ctx
        )
        neighbors = [{"node": others[_other_end(e, node_id)], "edge": e} for e in edges]
        return {"node": node, "neighbors": neighbors}

    async def get_subgraph(
        self, node_id: UUID, *, org_ctx: OrgContext, depth: int = 2
    ) -> dict:
        """Visible nodes within *depth* hops (through visible nodes only)."""
        if not await self._visible_nodes({node_id}, org_ctx):
            return {"nodes": [], "edges": []}
        seen = {node_id}
        frontier = {node_id}
        for _ in range(depth):
            reached: set[UUID] = set()
            for e in await self._visible_edges_touching(frontier, org_ctx):
                reached |= {e.from_node_id, e.to_node_id}
            frontier = reached - seen
            if not frontier:
                break
            seen |= frontier
        nodes = await self._visible_nodes(seen, org_ctx)
        edges = [
            e
            for e in await self._visible_edges_touching(seen, org_ctx)
            if e.from_node_id in seen and e.to_node_id in seen
        ]
        return {"nodes": list(nodes.values()), "edges": edges}

    # ------------------------------------------------------------------
    # Path finding -- breadth-first over visible nodes
    # ------------------------------------------------------------------

    async def find_path(
        self,
        from_id: UUID,
        to_id: UUID,
        *,
        org_ctx: OrgContext,
        max_depth: int = 10,
    ) -> list[dict]:
        """The shortest path between two visible nodes through visible nodes.

        Edges are undirected here.  Returns one dict per step (``node_id``,
        ``node_title``, ``node_type``, ``edge_id``, ``edge_type_id``; the
        edge fields are ``None`` for the start), or ``[]`` when there is no
        such path or either end is invisible.
        """
        ends = {from_id, to_id}
        if len(await self._visible_nodes(ends, org_ctx)) < len(ends):
            return []
        # node -> (previous node, edge that reached it)
        came_from: dict[UUID, tuple[UUID, Edge] | None] = {from_id: None}
        frontier = {from_id}
        for _ in range(max_depth):
            if to_id in came_from or not frontier:
                break
            reached: set[UUID] = set()
            for e in await self._visible_edges_touching(frontier, org_ctx):
                for here, there in (
                    (e.from_node_id, e.to_node_id),
                    (e.to_node_id, e.from_node_id),
                ):
                    if here in frontier and there not in came_from:
                        came_from[there] = (here, e)
                        reached.add(there)
            frontier = reached
        if to_id not in came_from:
            return []

        steps: list[tuple[UUID, Edge | None]] = []
        step: UUID | None = to_id
        while step is not None:
            prev = came_from[step]
            steps.append((step, prev[1] if prev else None))
            step = prev[0] if prev else None
        steps.reverse()

        nodes = await self._visible_nodes({nid for nid, _ in steps}, org_ctx)
        return [
            {
                "node_id": nid,
                "node_title": nodes[nid].title,
                "node_type": nodes[nid].node_type,
                "edge_id": edge.id if edge else None,
                "edge_type_id": edge.edge_type_id if edge else None,
            }
            for nid, edge in steps
        ]

    # ------------------------------------------------------------------
    # Full graph -- all visible nodes and edges, optionally filtered
    # ------------------------------------------------------------------

    async def get_full_graph(
        self,
        *,
        org_ctx: OrgContext,
        node_types: list[str] | None = None,
        edge_types: list[str] | None = None,
    ) -> dict:
        """Return all visible nodes and edges, optionally filtered by type.

        By default, politieke_input nodes are only included when they have
        at least one edge (i.e. they are connected to the policy graph).
        Edges are only returned when both ends are in the returned nodes.

        Returns ``{"nodes": [...], "edges": [...]}``.
        """
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
        nodes = list((await self.session.scalars(nodes_stmt)).all())
        node_ids = {n.id for n in nodes}

        edges_stmt = select(Edge).where(
            Edge.from_node_id.in_(node_ids),
            Edge.to_node_id.in_(node_ids),
        )
        if edge_types:
            edges_stmt = edges_stmt.where(Edge.edge_type_id.in_(edge_types))
        edges = list((await self.session.scalars(edges_stmt)).all())

        return {"nodes": nodes, "edges": edges}

    # ------------------------------------------------------------------
    # Community graph -- leads, people, orgs, corpus nodes and relations
    # ------------------------------------------------------------------

    async def get_community_graph(
        self,
        org_ctx: OrgContext | None = None,
        init_ctx: InitiatiefContext | None = None,
        initiatief_id: UUID | None = None,
        *,
        include_people: bool = True,
    ) -> CommunityGraphResponse:
        """Build a unified graph of leads, persons, organisations and corpus nodes.

        The graph starts from leads filtered by ``init_ctx`` (visibility) and,
        when ``initiatief_id`` is given, narrowed to that single initiatief.
        It then transitively collects every person, external organisation,
        samenwerkingsverband and corpus node connected to those leads.
        People (and what only they connect) are left out unless
        *include_people*.  A role held by an eenheid instead of a person
        connects to that eenheid.

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
        leads_stmt = apply_lead_filter(leads_stmt, init_ctx)
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

        # -- 2. Lead → OrganisatieEenheid edges (externe organisaties zijn nu
        # gewone OrganisatieEenheid-rijen) --
        org_ids = {
            lead.organisatie_eenheid_id
            for lead in leads
            if lead.organisatie_eenheid_id is not None
        }
        if org_ids:
            orgs_stmt = select(OrganisatieEenheid).where(
                OrganisatieEenheid.id.in_(org_ids)
            )
            orgs_result = await self.session.execute(orgs_stmt)
            for org in orgs_result.scalars().all():
                oid = f"org-{org.id}"
                graph_nodes[oid] = CommunityGraphNode(
                    id=oid,
                    node_type="organisation",
                    label=org.naam,
                    org_type=org.type,
                )

            for lead in leads:
                if lead.organisatie_eenheid_id is not None:
                    graph_edges.append(
                        CommunityGraphEdge(
                            id=_next_edge_id(),
                            source=f"lead-{lead.id}",
                            target=f"org-{lead.organisatie_eenheid_id}",
                            edge_type="organisatie",
                            label="externe organisatie",
                        )
                    )

        # -- 2b. Lead → organisation (free-text field) --
        for lead in leads:
            if lead.organization and not lead.organisatie_eenheid_id:
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
        # Eenheden holding a role on a lead or corpus node themselves.
        grant_eenheid_ids = set[UUID]()

        def _grant_target(grant: ResourcePermission, persons: set[UUID]) -> str | None:
            """The graph key a role points to, collecting its holder; None: skip."""
            if grant.person_id is None:
                grant_eenheid_ids.add(grant.organisatie_eenheid_id)
                return f"oe-{grant.organisatie_eenheid_id}"
            if not include_people:
                return None
            person_ids.add(grant.person_id)
            persons.add(grant.person_id)
            return f"person-{grant.person_id}"

        for lead in leads:
            if include_people and lead.assignee_id is not None:
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
            target = _grant_target(contact, external_person_ids)
            if target is None:
                continue
            graph_edges.append(
                CommunityGraphEdge(
                    id=_next_edge_id(),
                    source=f"lead-{contact.resource_id}",
                    target=target,
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
                target = _grant_target(sh, internal_person_ids)
                if target is None:
                    continue
                graph_edges.append(
                    CommunityGraphEdge(
                        id=_next_edge_id(),
                        source=f"node-{sh.resource_id}",
                        target=target,
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

        # -- 9. Person → OrganisatieEenheid (active plaatsingen), and the
        # eenheden holding a role themselves --
        oe_ids = set(grant_eenheid_ids)
        plaatsing_rows: list[PersonOrganisatieEenheid] = []
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
            plaatsing_rows = list(plaatsingen_result.scalars().all())
            oe_ids |= {pl.organisatie_eenheid_id for pl in plaatsing_rows}

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
