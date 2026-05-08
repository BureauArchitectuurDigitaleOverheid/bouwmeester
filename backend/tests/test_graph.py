"""Comprehensive API tests for the graph router."""

import uuid
from datetime import date

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge
from bouwmeester.models.lead import Lead
from bouwmeester.models.persoon_samenwerkingsverband import (
    PersoonSamenwerkingsverband,
)
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.samenwerkingsverband import Samenwerkingsverband

# ---------------------------------------------------------------------------
# Graph search
# ---------------------------------------------------------------------------


async def test_graph_search_returns_200(client):
    """GET /api/graph/search returns 200 and a graph view."""
    resp = await client.get("/api/graph/search")
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "edges" in data
    assert isinstance(data["nodes"], list)
    assert isinstance(data["edges"], list)


async def test_graph_search_with_data(client, sample_node, sample_edge):
    """GET /api/graph/search returns nodes and edges when data exists."""
    resp = await client.get("/api/graph/search")
    assert resp.status_code == 200
    data = resp.json()
    node_ids = {n["id"] for n in data["nodes"]}
    assert str(sample_node.id) in node_ids
    edge_ids = {e["id"] for e in data["edges"]}
    assert str(sample_edge.id) in edge_ids


async def test_graph_search_filter_by_node_type(client, sample_node):
    """GET /api/graph/search?node_types=dossier filters by node type."""
    resp = await client.get("/api/graph/search", params={"node_types": "dossier"})
    assert resp.status_code == 200
    data = resp.json()
    for n in data["nodes"]:
        assert n["node_type"] == "dossier"


async def test_graph_search_with_long_title(client, db_session, sample_edge_type):
    """Nodes with titles > 500 chars must not crash graph/search (regression #107)."""
    long_title = "A" * 719  # reproduces parlementaire import with long onderwerp
    node = CorpusNode(
        id=uuid.uuid4(),
        title=long_title,
        node_type="politieke_input",
        description="Test node with long title",
        status="actief",
    )
    # PI nodes need at least one edge to appear in the graph
    anchor = CorpusNode(
        id=uuid.uuid4(),
        title="Anchor dossier",
        node_type="dossier",
        status="actief",
    )
    db_session.add_all([node, anchor])
    await db_session.flush()
    db_session.add(
        Edge(
            id=uuid.uuid4(),
            from_node_id=node.id,
            to_node_id=anchor.id,
            edge_type_id=sample_edge_type.id,
        )
    )
    await db_session.flush()

    resp = await client.get("/api/graph/search")
    assert resp.status_code == 200
    data = resp.json()
    node_ids = {n["id"] for n in data["nodes"]}
    assert str(node.id) in node_ids
    # The long title must be returned in full
    matched = [n for n in data["nodes"] if n["id"] == str(node.id)]
    assert matched[0]["title"] == long_title


async def test_list_nodes_with_long_title(client, db_session, sample_edge_type):
    """Nodes list must not 500 on titles > 500 chars (regression #107)."""
    long_title = "B" * 600
    node = CorpusNode(
        id=uuid.uuid4(),
        title=long_title,
        node_type="politieke_input",
        description="Test node with long title",
        status="actief",
    )
    # PI nodes need at least one edge to appear in the list
    anchor = CorpusNode(
        id=uuid.uuid4(),
        title="Anchor dossier",
        node_type="dossier",
        status="actief",
    )
    db_session.add_all([node, anchor])
    await db_session.flush()
    db_session.add(
        Edge(
            id=uuid.uuid4(),
            from_node_id=node.id,
            to_node_id=anchor.id,
            edge_type_id=sample_edge_type.id,
        )
    )
    await db_session.flush()

    resp = await client.get("/api/nodes", params={"node_type": "politieke_input"})
    assert resp.status_code == 200
    data = resp.json()
    node_ids = {n["id"] for n in data}
    assert str(node.id) in node_ids


# ---------------------------------------------------------------------------
# Unconnected politieke_input filtering
# ---------------------------------------------------------------------------


async def test_unconnected_pi_hidden_from_node_list(client, db_session):
    """Unconnected politieke_input nodes are excluded from GET /api/nodes."""
    node = CorpusNode(
        id=uuid.uuid4(),
        title="Orphan PI",
        node_type="politieke_input",
        description="No edges",
        status="actief",
    )
    db_session.add(node)
    await db_session.flush()

    resp = await client.get("/api/nodes", params={"node_type": "politieke_input"})
    assert resp.status_code == 200
    node_ids = {n["id"] for n in resp.json()}
    assert str(node.id) not in node_ids


async def test_unconnected_pi_shown_with_include_flag(client, db_session):
    """include_unconnected_pi=true makes unconnected PI nodes visible."""
    node = CorpusNode(
        id=uuid.uuid4(),
        title="Included Orphan PI",
        node_type="politieke_input",
        description="No edges but explicitly included",
        status="actief",
    )
    db_session.add(node)
    await db_session.flush()

    resp = await client.get(
        "/api/nodes",
        params={"node_type": "politieke_input", "include_unconnected_pi": "true"},
    )
    assert resp.status_code == 200
    node_ids = {n["id"] for n in resp.json()}
    assert str(node.id) in node_ids


async def test_unconnected_pi_hidden_from_graph(client, db_session):
    """Unconnected politieke_input nodes are excluded from the graph view."""
    node = CorpusNode(
        id=uuid.uuid4(),
        title="Graph Orphan PI",
        node_type="politieke_input",
        description="No edges",
        status="actief",
    )
    db_session.add(node)
    await db_session.flush()

    resp = await client.get("/api/graph/search")
    assert resp.status_code == 200
    node_ids = {n["id"] for n in resp.json()["nodes"]}
    assert str(node.id) not in node_ids


# ---------------------------------------------------------------------------
# Find path
# ---------------------------------------------------------------------------


async def test_find_path_returns_200(client, sample_node, second_node, sample_edge):
    """GET /api/graph/path?from_id=...&to_id=... returns a path result."""
    resp = await client.get(
        "/api/graph/path",
        params={
            "from_id": str(sample_node.id),
            "to_id": str(second_node.id),
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "from_id" in data
    assert "to_id" in data
    assert "path" in data
    assert "length" in data
    assert data["from_id"] == str(sample_node.id)
    assert data["to_id"] == str(second_node.id)


# ---------------------------------------------------------------------------
# Community graph -- person_role (intern vs extern)
# ---------------------------------------------------------------------------


async def test_community_graph_assignee_is_intern(client, db_session, sample_person):
    """A lead assignee shows up as person_role='intern' in the community graph."""
    lead = Lead(
        id=uuid.uuid4(),
        title="Lead met assignee",
        stage="verkennen",
        assignee_id=sample_person.id,
    )
    db_session.add(lead)
    await db_session.flush()

    resp = await client.get("/api/graph/community")
    assert resp.status_code == 200
    data = resp.json()
    person_node = next(
        (n for n in data["nodes"] if n["id"] == f"person-{sample_person.id}"),
        None,
    )
    assert person_node is not None
    assert person_node["person_role"] == "intern"


async def test_community_graph_lead_contact_is_extern(
    client, db_session, sample_person
):
    """A lead-contact-only person shows up as person_role='extern'."""
    lead = Lead(
        id=uuid.uuid4(),
        title="Lead met externe contact",
        stage="verkennen",
    )
    db_session.add(lead)
    await db_session.flush()

    db_session.add(
        ResourcePermission(
            id=uuid.uuid4(),
            resource_type="lead",
            resource_id=lead.id,
            person_id=sample_person.id,
            rol="contactpersoon",
        )
    )
    await db_session.flush()

    resp = await client.get("/api/graph/community")
    assert resp.status_code == 200
    data = resp.json()
    person_node = next(
        (n for n in data["nodes"] if n["id"] == f"person-{sample_person.id}"),
        None,
    )
    assert person_node is not None
    assert person_node["person_role"] == "extern"


async def test_community_graph_intern_wins_over_extern(
    client, db_session, sample_person
):
    """Iemand die zowel assignee als externe contact is, krijgt 'intern'."""
    lead_a = Lead(
        id=uuid.uuid4(),
        title="Lead A (assignee)",
        stage="verkennen",
        assignee_id=sample_person.id,
    )
    lead_b = Lead(
        id=uuid.uuid4(),
        title="Lead B (externe contact)",
        stage="verkennen",
    )
    db_session.add_all([lead_a, lead_b])
    await db_session.flush()

    db_session.add(
        ResourcePermission(
            id=uuid.uuid4(),
            resource_type="lead",
            resource_id=lead_b.id,
            person_id=sample_person.id,
            rol="contactpersoon",
        )
    )
    await db_session.flush()

    resp = await client.get("/api/graph/community")
    assert resp.status_code == 200
    data = resp.json()
    person_node = next(
        (n for n in data["nodes"] if n["id"] == f"person-{sample_person.id}"),
        None,
    )
    assert person_node is not None
    assert person_node["person_role"] == "intern"


async def test_community_graph_org_with_internal_person_is_intern(
    client, db_session, sample_person, sample_organisatie
):
    """Een OrganisatieEenheid waar een interne persoon (lead-assignee) actief
    in geplaatst is, krijgt org_role='intern' — zodat de frontend deze in de
    onderste swim-lane kan zetten."""
    from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid

    lead = Lead(
        id=uuid.uuid4(),
        title="Lead met interne assignee",
        stage="verkennen",
        assignee_id=sample_person.id,
    )
    db_session.add(lead)
    db_session.add(
        PersonOrganisatieEenheid(
            id=uuid.uuid4(),
            person_id=sample_person.id,
            organisatie_eenheid_id=sample_organisatie.id,
            start_datum=date.today(),
        )
    )
    await db_session.flush()

    resp = await client.get("/api/graph/community")
    assert resp.status_code == 200
    org_node = next(
        (n for n in resp.json()["nodes"] if n["id"] == f"oe-{sample_organisatie.id}"),
        None,
    )
    assert org_node is not None
    assert org_node["org_role"] == "intern"


async def test_community_graph_externe_organisatie_is_extern(
    client, db_session, sample_person
):
    """Een ExterneOrganisatie die via een lead in de graph terechtkomt krijgt
    org_role='extern'."""
    from bouwmeester.models.externe_organisatie import ExterneOrganisatie

    ext_org = ExterneOrganisatie(
        id=uuid.uuid4(),
        naam="Externe Adviesbureau BV",
        type="marktpartij",
    )
    db_session.add(ext_org)
    await db_session.flush()

    lead = Lead(
        id=uuid.uuid4(),
        title="Lead met externe organisatie",
        stage="verkennen",
        assignee_id=sample_person.id,
        externe_organisatie_id=ext_org.id,
    )
    db_session.add(lead)
    await db_session.flush()

    resp = await client.get("/api/graph/community")
    assert resp.status_code == 200
    ext_node = next(
        (n for n in resp.json()["nodes"] if n["id"] == f"org-{ext_org.id}"),
        None,
    )
    assert ext_node is not None
    assert ext_node["org_role"] == "extern"


async def test_community_graph_org_with_only_external_person_is_extern(
    client, db_session, sample_person, sample_organisatie
):
    """Een OrganisatieEenheid waar alleen een externe contact in geplaatst is,
    krijgt org_role='extern'. Dit voorkomt dat een gemeente die toevallig als
    OrganisatieEenheid bestaat onderaan terechtkomt zodra een externe contact
    daar gekoppeld is."""
    from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid

    lead = Lead(
        id=uuid.uuid4(),
        title="Lead met externe contact in OE",
        stage="verkennen",
    )
    db_session.add(lead)
    await db_session.flush()
    db_session.add(
        ResourcePermission(
            id=uuid.uuid4(),
            resource_type="lead",
            resource_id=lead.id,
            person_id=sample_person.id,
            rol="contactpersoon",
        )
    )
    db_session.add(
        PersonOrganisatieEenheid(
            id=uuid.uuid4(),
            person_id=sample_person.id,
            organisatie_eenheid_id=sample_organisatie.id,
            start_datum=date.today(),
        )
    )
    await db_session.flush()

    resp = await client.get("/api/graph/community")
    assert resp.status_code == 200
    org_node = next(
        (n for n in resp.json()["nodes"] if n["id"] == f"oe-{sample_organisatie.id}"),
        None,
    )
    assert org_node is not None
    assert org_node["org_role"] == "extern"


async def test_community_graph_contact_edge_label_is_externe_contactpersoon(
    client, db_session, sample_person
):
    """Lead → person contact-edges met rol 'contactpersoon' krijgen het UI-label."""
    lead = Lead(
        id=uuid.uuid4(),
        title="Lead met externe contact",
        stage="verkennen",
    )
    db_session.add(lead)
    await db_session.flush()

    db_session.add(
        ResourcePermission(
            id=uuid.uuid4(),
            resource_type="lead",
            resource_id=lead.id,
            person_id=sample_person.id,
            rol="contactpersoon",
        )
    )
    await db_session.flush()

    resp = await client.get("/api/graph/community")
    assert resp.status_code == 200
    contact_edges = [
        e
        for e in resp.json()["edges"]
        if e["source"] == f"lead-{lead.id}"
        and e["target"] == f"person-{sample_person.id}"
        and e["edge_type"] == "contact"
    ]
    assert len(contact_edges) == 1
    assert contact_edges[0]["label"] == "externe contactpersoon"


async def test_community_graph_renders_samenwerkingsverband(
    client, db_session, sample_person
):
    """Een persoon met actief swv-lidmaatschap krijgt een swv-node + edge."""
    lead = Lead(
        id=uuid.uuid4(),
        title="Lead met swv-lid",
        stage="verkennen",
        assignee_id=sample_person.id,
    )
    db_session.add(lead)

    swv = Samenwerkingsverband(
        id=uuid.uuid4(),
        naam="CRI",
        type="programma",
    )
    db_session.add(swv)
    await db_session.flush()

    db_session.add(
        PersoonSamenwerkingsverband(
            id=uuid.uuid4(),
            person_id=sample_person.id,
            samenwerkingsverband_id=swv.id,
            rol="trekker",
            start_datum=date.today(),
        )
    )
    await db_session.flush()

    resp = await client.get("/api/graph/community")
    assert resp.status_code == 200
    data = resp.json()

    swv_node = next(
        (n for n in data["nodes"] if n["id"] == f"swv-{swv.id}"),
        None,
    )
    assert swv_node is not None
    assert swv_node["node_type"] == "samenwerkingsverband"
    assert swv_node["label"] == "CRI"
    assert swv_node["samenwerkingsverband_type"] == "programma"

    swv_edge = next(
        (
            e
            for e in data["edges"]
            if e["source"] == f"person-{sample_person.id}"
            and e["target"] == f"swv-{swv.id}"
            and e["edge_type"] == "lid_van_swv"
        ),
        None,
    )
    assert swv_edge is not None
    assert swv_edge["label"] == "trekker"


async def test_community_graph_filters_by_initiatief_id_query_param(
    client, db_session, sample_person
):
    """initiatief_id query-param beperkt de graaf tot die ene initiatief.

    Voorheen filterde alleen de frontend op `lead.initiatiefId`, waardoor
    persons en organisations die aan leads van een ander initiatief
    hingen wel in de respons stonden en in de UI 'rondzwommen'.
    """
    from bouwmeester.models.initiatief import Initiatief

    init_a = Initiatief(id=uuid.uuid4(), naam="Init A")
    init_b = Initiatief(id=uuid.uuid4(), naam="Init B")
    db_session.add_all([init_a, init_b])
    await db_session.flush()

    lead_a = Lead(
        id=uuid.uuid4(),
        title="Lead in A",
        stage="verkennen",
        initiatief_id=init_a.id,
        assignee_id=sample_person.id,
    )
    lead_b = Lead(
        id=uuid.uuid4(),
        title="Lead in B",
        stage="verkennen",
        initiatief_id=init_b.id,
    )
    db_session.add_all([lead_a, lead_b])
    await db_session.flush()

    resp = await client.get(f"/api/graph/community?initiatief_id={init_a.id}")
    assert resp.status_code == 200
    data = resp.json()

    lead_ids = {n["id"] for n in data["nodes"] if n["node_type"] == "lead"}
    assert f"lead-{lead_a.id}" in lead_ids
    assert f"lead-{lead_b.id}" not in lead_ids

    person_ids = {n["id"] for n in data["nodes"] if n["node_type"] == "person"}
    assert f"person-{sample_person.id}" in person_ids


async def test_community_graph_excludes_persons_from_other_initiatief(
    client, db_session, create_person
):
    """Een persoon die alleen via een lead van een ander initiatief in de
    graaf zou komen, mag bij filtering op initiatief_id niet meer verschijnen.
    """
    from bouwmeester.models.initiatief import Initiatief

    init_a = Initiatief(id=uuid.uuid4(), naam="Init A")
    init_b = Initiatief(id=uuid.uuid4(), naam="Init B")
    db_session.add_all([init_a, init_b])

    person_a = await create_person(naam="Alice")
    person_b = await create_person(naam="Bob")

    db_session.add_all(
        [
            Lead(
                id=uuid.uuid4(),
                title="Lead in A",
                stage="verkennen",
                initiatief_id=init_a.id,
                assignee_id=person_a.id,
            ),
            Lead(
                id=uuid.uuid4(),
                title="Lead in B",
                stage="verkennen",
                initiatief_id=init_b.id,
                assignee_id=person_b.id,
            ),
        ]
    )
    await db_session.flush()

    resp = await client.get(f"/api/graph/community?initiatief_id={init_a.id}")
    assert resp.status_code == 200
    data = resp.json()

    person_ids = {n["id"] for n in data["nodes"] if n["node_type"] == "person"}
    assert f"person-{person_a.id}" in person_ids
    assert f"person-{person_b.id}" not in person_ids
