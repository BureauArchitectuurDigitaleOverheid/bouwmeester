"""Pydantic schemas for the community graph endpoint."""

from pydantic import BaseModel, ConfigDict


class CommunityGraphNode(BaseModel):
    """A node in the community graph (lead, person, organisation, or corpus node)."""

    # id is prefixed: "lead-{uuid}" | "person-{uuid}" | "oe-{uuid}" |
    # "node-{uuid}" | "swv-{uuid}"
    id: str
    # one of: "lead", "person", "organisation", "corpus_node",
    # "samenwerkingsverband"
    node_type: str
    label: str
    # Type-specific metadata
    stage: str | None = None  # for leads
    initiatief_id: str | None = None  # for leads
    functie: str | None = None  # for persons
    expertise: str | None = None  # for persons
    person_role: str | None = None  # "intern" | "extern" — for persons
    org_type: str | None = None  # for organisations
    org_role: str | None = None  # "intern" | "extern" — for organisations
    samenwerkingsverband_type: str | None = None  # for samenwerkingsverbanden
    corpus_node_type: str | None = None  # for corpus nodes

    model_config = ConfigDict(from_attributes=True)


class CommunityGraphEdge(BaseModel):
    """An edge in the community graph."""

    id: str
    source: str  # prefixed node ID
    target: str  # prefixed node ID
    # verantwoordelijke | contact | organisatie | gelinkt |
    # stakeholder role | lid_van | corpus edge_type_id
    edge_type: str
    label: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CommunityGraphResponse(BaseModel):
    """Full community graph response."""

    nodes: list[CommunityGraphNode]
    edges: list[CommunityGraphEdge]
