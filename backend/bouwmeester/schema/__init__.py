"""Pydantic schemas for the Bouwmeester API."""

from bouwmeester.schema.access_request import (
    AccessRequestCreate,
    AccessRequestResponse,
    AccessRequestReviewRequest,
    AccessRequestStatusResponse,
)
from bouwmeester.schema.activity import ActivityFeedResponse, ActivityResponse
from bouwmeester.schema.app_config import AppConfigResponse, AppConfigUpdate
from bouwmeester.schema.bron import (
    BronBijlageResponse,
    BronCreate,
    BronResponse,
    BronUpdate,
)
from bouwmeester.schema.corpus_node import (
    CorpusNodeBase,
    CorpusNodeCreate,
    CorpusNodeResponse,
    CorpusNodeUpdate,
    CorpusNodeWithEdges,
    NodeStatusRecord,
    NodeTitleRecord,
    NodeType,
)
from bouwmeester.schema.database_backup import (
    DatabaseBackupInfo,
    DatabaseResetRequest,
    DatabaseResetResult,
    DatabaseRestoreResult,
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
from bouwmeester.schema.llm import (
    EdgeSuggestionItem,
    EdgeSuggestionRequest,
    EdgeSuggestionResponse,
    SummarizeRequest,
    SummarizeResponse,
    TagSuggestionRequest,
    TagSuggestionResponse,
)
from bouwmeester.schema.mention import (
    MentionCreate,
    MentionReference,
    MentionResponse,
    MentionSearchResult,
)
from bouwmeester.schema.organisatie_eenheid import (
    OrganisatieEenheidCreate,
    OrganisatieEenheidPersonenGroup,
    OrganisatieEenheidResponse,
    OrganisatieEenheidTreeNode,
    OrganisatieEenheidUpdate,
    OrgManagerRecord,
    OrgNaamRecord,
    OrgParentRecord,
)
from bouwmeester.schema.parlementair_item import (
    ParlementairItemResponse,
    ReviewAction,
    SuggestedEdgeResponse,
)
from bouwmeester.schema.person import (
    PHONE_LABELS,
    ApiKeyResponse,
    OnboardingRequest,
    PersonBase,
    PersonCreate,
    PersonCreateResponse,
    PersonDetailResponse,
    PersonEmailCreate,
    PersonEmailResponse,
    PersonPhoneCreate,
    PersonPhoneResponse,
    PersonResponse,
    PersonSummaryResponse,
    PersonUpdate,
)
from bouwmeester.schema.search import SearchResponse, SearchResult, SearchResultType
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
from bouwmeester.schema.webauthn import (
    AuthenticateOptionsRequest,
    AuthenticateVerifyRequest,
    RegisterVerifyRequest,
    WebAuthnCredentialResponse,
)
from bouwmeester.schema.whitelist import (
    AdminToggleRequest,
    AdminUserResponse,
    WhitelistEmailCreate,
    WhitelistEmailResponse,
)

# Resolve forward references between corpus_node <-> edge schemas.
CorpusNodeWithEdges.model_rebuild()
OrganisatieEenheidTreeNode.model_rebuild()
OrganisatieEenheidPersonenGroup.model_rebuild()
TagTreeResponse.model_rebuild()

__all__ = [
    # access_request
    "AccessRequestCreate",
    "AccessRequestResponse",
    "AccessRequestReviewRequest",
    "AccessRequestStatusResponse",
    # bron
    "BronBijlageResponse",
    "BronCreate",
    "BronResponse",
    "BronUpdate",
    # corpus_node
    "CorpusNodeBase",
    "CorpusNodeCreate",
    "CorpusNodeResponse",
    "CorpusNodeUpdate",
    "CorpusNodeWithEdges",
    "NodeStatusRecord",
    "NodeTitleRecord",
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
    "OrgManagerRecord",
    "OrgNaamRecord",
    "OrgParentRecord",
    "OrganisatieEenheidCreate",
    "OrganisatieEenheidPersonenGroup",
    "OrganisatieEenheidResponse",
    "OrganisatieEenheidTreeNode",
    "OrganisatieEenheidUpdate",
    # person
    "ApiKeyResponse",
    "OnboardingRequest",
    "PHONE_LABELS",
    "PersonBase",
    "PersonCreate",
    "PersonCreateResponse",
    "PersonDetailResponse",
    "PersonEmailCreate",
    "PersonEmailResponse",
    "PersonPhoneCreate",
    "PersonPhoneResponse",
    "PersonResponse",
    "PersonSummaryResponse",
    "PersonUpdate",
    # activity
    "ActivityFeedResponse",
    "ActivityResponse",
    # app_config
    "AppConfigResponse",
    "AppConfigUpdate",
    # database_backup
    "DatabaseBackupInfo",
    "DatabaseResetRequest",
    "DatabaseResetResult",
    "DatabaseRestoreResult",
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
    "SearchResultType",
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
    # llm
    "EdgeSuggestionItem",
    "EdgeSuggestionRequest",
    "EdgeSuggestionResponse",
    "SummarizeRequest",
    "SummarizeResponse",
    "TagSuggestionRequest",
    "TagSuggestionResponse",
    # parlementair_item
    "ParlementairItemResponse",
    "ReviewAction",
    "SuggestedEdgeResponse",
    # whitelist / admin
    "AdminToggleRequest",
    "AdminUserResponse",
    # webauthn
    "AuthenticateOptionsRequest",
    "AuthenticateVerifyRequest",
    "RegisterVerifyRequest",
    "WebAuthnCredentialResponse",
    "WhitelistEmailCreate",
    "WhitelistEmailResponse",
]
