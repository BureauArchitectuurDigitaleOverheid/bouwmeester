"""Pydantic schemas for the Bouwmeester API."""

from bouwmeester.schema.activity import ActivityResponse
from bouwmeester.schema.corpus_node import (
    CorpusNodeBase,
    CorpusNodeCreate,
    CorpusNodeResponse,
    CorpusNodeUpdate,
    CorpusNodeWithEdges,
    NodeType,
)
from bouwmeester.schema.edge import (
    EdgeBase,
    EdgeCreate,
    EdgeResponse,
    EdgeUpdate,
    EdgeWithNodes,
)
from bouwmeester.schema.edge_type import EdgeTypeBase, EdgeTypeCreate, EdgeTypeResponse
from bouwmeester.schema.graph import (
    GraphNeighborsResponse,
    GraphSearchParams,
    GraphViewResponse,
    NeighborEntry,
)
from bouwmeester.schema.inbox import InboxItem, InboxResponse
from bouwmeester.schema.mention import (
    MentionCreate,
    MentionReference,
    MentionResponse,
    MentionSearchResult,
)
from bouwmeester.schema.motie_import import (
    MotieImportResponse,
    ReviewAction,
    SuggestedEdgeResponse,
)
from bouwmeester.schema.organisatie_eenheid import (
    OrganisatieEenheidCreate,
    OrganisatieEenheidPersonenGroup,
    OrganisatieEenheidResponse,
    OrganisatieEenheidTreeNode,
    OrganisatieEenheidUpdate,
)
from bouwmeester.schema.person import (
    PersonBase,
    PersonCreate,
    PersonDetailResponse,
    PersonResponse,
    PersonSummaryResponse,
    PersonUpdate,
)
from bouwmeester.schema.search import SearchResponse, SearchResult
from bouwmeester.schema.tag import (
    NodeTagCreate,
    NodeTagResponse,
    TagBase,
    TagCreate,
    TagResponse,
    TagTreeResponse,
    TagUpdate,
)
from bouwmeester.schema.task import (
    EenheidOverviewResponse,
    EenheidPersonTaskStats,
    EenheidSubeenheidStats,
    TaskBase,
    TaskCreate,
    TaskOrgEenheidSummary,
    TaskPriority,
    TaskResponse,
    TaskStatus,
    TaskSubtaskSummary,
    TaskUpdate,
)

# Resolve forward references between corpus_node <-> edge schemas.
CorpusNodeWithEdges.model_rebuild()
OrganisatieEenheidTreeNode.model_rebuild()
OrganisatieEenheidPersonenGroup.model_rebuild()
TagTreeResponse.model_rebuild()

__all__ = [
    # corpus_node
    "CorpusNodeBase",
    "CorpusNodeCreate",
    "CorpusNodeResponse",
    "CorpusNodeUpdate",
    "CorpusNodeWithEdges",
    "NodeType",
    # edge
    "EdgeBase",
    "EdgeCreate",
    "EdgeResponse",
    "EdgeUpdate",
    "EdgeWithNodes",
    # edge_type
    "EdgeTypeBase",
    "EdgeTypeCreate",
    "EdgeTypeResponse",
    # task
    "EenheidOverviewResponse",
    "EenheidPersonTaskStats",
    "EenheidSubeenheidStats",
    "TaskBase",
    "TaskCreate",
    "TaskOrgEenheidSummary",
    "TaskPriority",
    "TaskResponse",
    "TaskStatus",
    "TaskSubtaskSummary",
    "TaskUpdate",
    # organisatie_eenheid
    "OrganisatieEenheidCreate",
    "OrganisatieEenheidPersonenGroup",
    "OrganisatieEenheidResponse",
    "OrganisatieEenheidTreeNode",
    "OrganisatieEenheidUpdate",
    # person
    "PersonBase",
    "PersonCreate",
    "PersonDetailResponse",
    "PersonResponse",
    "PersonSummaryResponse",
    "PersonUpdate",
    # activity
    "ActivityResponse",
    # graph
    "GraphNeighborsResponse",
    "GraphSearchParams",
    "GraphViewResponse",
    "NeighborEntry",
    # inbox
    "InboxItem",
    "InboxResponse",
    # search
    "SearchResponse",
    "SearchResult",
    # tag
    "NodeTagCreate",
    "NodeTagResponse",
    "TagBase",
    "TagCreate",
    "TagResponse",
    "TagTreeResponse",
    "TagUpdate",
    # mention
    "MentionCreate",
    "MentionReference",
    "MentionResponse",
    "MentionSearchResult",
    # motie_import
    "MotieImportResponse",
    "ReviewAction",
    "SuggestedEdgeResponse",
]
