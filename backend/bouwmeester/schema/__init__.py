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
from bouwmeester.schema.chat import (
    ChatAction,
    ChatAttachmentResponse,
    ChatConfirmRequest,
    ChatConfirmResponse,
    ChatContext,
    ChatConversationHistoryResponse,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    PendingAction,
)
from bouwmeester.schema.community_graph import (
    CommunityGraphEdge,
    CommunityGraphNode,
    CommunityGraphResponse,
)
from bouwmeester.schema.corpus_node import (
    BeleidskompasProgress,
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
from bouwmeester.schema.edge_schema_rule import (
    EdgeSchemaRuleCreate,
    EdgeSchemaRuleResponse,
    ValidEdgeTypesResponse,
)
from bouwmeester.schema.edge_type import EdgeTypeBase, EdgeTypeCreate, EdgeTypeResponse
from bouwmeester.schema.eenheid_module import (  # noqa: F401
    EenheidModuleResponse,
    EenheidModulesResponse,
    EenheidModuleUpdate,
)
from bouwmeester.schema.externe_organisatie import (
    ExterneOrganisatieCreate,
    ExterneOrganisatieResponse,
    ExterneOrganisatieUpdate,
)
from bouwmeester.schema.fcc import (
    FccConflictResolution,
    FccConflictResolveRequest,
    FccSchemaResponse,
    FccSyncLogResponse,
    FccSyncTriggerResponse,
)
from bouwmeester.schema.graph import (
    GraphNeighborsResponse,
    GraphSearchParams,
    GraphViewResponse,
    NeighborEntry,
)
from bouwmeester.schema.inbox import InboxItem, InboxResponse
from bouwmeester.schema.initiatief import (
    InitiatiefCreate,
    InitiatiefDetailResponse,
    InitiatiefEenheidCreate,
    InitiatiefEenheidResponse,
    InitiatiefMemberCreate,
    InitiatiefMemberResponse,
    InitiatiefResponse,
    InitiatiefUpdate,
)
from bouwmeester.schema.lead import (
    LeadActivityCreate,
    LeadActivityResponse,
    LeadActivityType,
    LeadAssigneeSummary,
    LeadAttachmentResponse,
    LeadBase,
    LeadContactCreate,
    LeadContactResponse,
    LeadCreate,
    LeadDetailResponse,
    LeadExterneOrgSummary,
    LeadInitiatiefSummary,
    LeadMergeRequest,
    LeadMetricsResponse,
    LeadMove,
    LeadNodeCreate,
    LeadNodeResponse,
    LeadParseResult,
    LeadReorder,
    LeadResponse,
    LeadStage,
    LeadTimelineEvent,
    LeadTimelineResponse,
    LeadUpdate,
)
from bouwmeester.schema.llm import (
    CorpusGapOverviewResponse,
    CorpusGapSummaryItem,
    EdgeSuggestionItem,
    GapAnalysisRequest,
    GapAnalysisResponse,
    GapItem,
    KompasGuidanceRequest,
    KompasGuidanceResponse,
    TagSuggestionRequest,
    TagSuggestionResponse,
)
from bouwmeester.schema.mattermost_user import (
    MattermostLinkCodeResponse,
    MattermostLinkStatusResponse,
    MattermostUserResponse,
    MattermostVerifyLinkRequest,
)
from bouwmeester.schema.mention import (
    MentionCreate,
    MentionReference,
    MentionResponse,
    MentionSearchResult,
)
from bouwmeester.schema.opdracht import (
    FinancieelJaar,
    FinancieelOverzicht,
    OpdrachtCreate,
    OpdrachtenSummary,
    OpdrachtNodeCreate,
    OpdrachtNodeResponse,
    OpdrachtResponse,
    OpdrachtUpdate,
)
from bouwmeester.schema.org_placement import (
    OrgPlacementRequestCreate,
    OrgPlacementRequestDecision,
    OrgPlacementRequestResponse,
    PlacementStatus,
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
from bouwmeester.schema.resource_permission import (
    ResourcePermissionCreate,
    ResourcePermissionResponse,
    ResourcePermissionUpdate,
)
from bouwmeester.schema.role import (
    MyPermissionsResponse,
    PermissionResponse,
    PersonRoleCreate,
    PersonRoleResponse,
    RoleResponse,
    RoleWithPermissionsResponse,
)
from bouwmeester.schema.search import (
    SearchResponse,
    SearchResult,
    SearchResultType,
    SimilarNodeItem,
    SimilarNodesResponse,
)
from bouwmeester.schema.shared_access import SharedAccessCreate, SharedAccessResponse
from bouwmeester.schema.tag import (
    LeadTagCreate,
    LeadTagResponse,
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
    TaskOpdrachtSummary,
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
    # community_graph
    "CommunityGraphEdge",
    "CommunityGraphNode",
    "CommunityGraphResponse",
    # chat
    "ChatAction",
    "ChatAttachmentResponse",
    "ChatConfirmRequest",
    "ChatConfirmResponse",
    "ChatContext",
    "ChatConversationHistoryResponse",
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "PendingAction",
    # bron
    "BronBijlageResponse",
    "BronCreate",
    "BronResponse",
    "BronUpdate",
    # corpus_node
    "BeleidskompasProgress",
    "CorpusNodeBase",
    "CorpusNodeCreate",
    "CorpusNodeResponse",
    "CorpusNodeUpdate",
    "CorpusNodeWithEdges",
    "NodeStatusRecord",
    "NodeTitleRecord",
    "NodeType",
    # externe_organisatie
    "ExterneOrganisatieCreate",
    "ExterneOrganisatieResponse",
    "ExterneOrganisatieUpdate",
    # edge
    "EenheidModuleResponse",
    "EenheidModulesResponse",
    "EenheidModuleUpdate",
    "EdgeBase",
    "EdgeCreate",
    "EdgeResponse",
    "EdgeUpdate",
    "EdgeWithNodes",
    # edge_schema_rule
    "EdgeSchemaRuleCreate",
    "EdgeSchemaRuleResponse",
    "ValidEdgeTypesResponse",
    # edge_type
    "EdgeTypeBase",
    "EdgeTypeCreate",
    "EdgeTypeResponse",
    # initiatief
    "InitiatiefCreate",
    "InitiatiefDetailResponse",
    "InitiatiefMemberCreate",
    "InitiatiefMemberResponse",
    "InitiatiefResponse",
    "InitiatiefEenheidCreate",
    "InitiatiefEenheidResponse",
    "InitiatiefUpdate",
    # task
    "EenheidOverviewResponse",
    "EenheidPersonTaskStats",
    "EenheidSubeenheidStats",
    "TaskBase",
    "TaskCreate",
    "TaskOpdrachtSummary",
    "TaskOrgEenheidSummary",
    "TaskPriority",
    "TaskResponse",
    "TaskStatus",
    "TaskSubtaskSummary",
    "TaskUpdate",
    # fcc
    "FccConflictResolveRequest",
    "FccConflictResolution",
    "FccSchemaResponse",
    "FccSyncLogResponse",
    "FccSyncTriggerResponse",
    # opdracht
    "FinancieelJaar",
    "FinancieelOverzicht",
    "OpdrachtCreate",
    "OpdrachtNodeCreate",
    "OpdrachtNodeResponse",
    "OpdrachtResponse",
    "OpdrachtenSummary",
    "OpdrachtUpdate",
    # org_placement
    "OrgPlacementRequestCreate",
    "OrgPlacementRequestDecision",
    "OrgPlacementRequestResponse",
    "PlacementStatus",
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
    # lead
    "LeadActivityCreate",
    "LeadActivityResponse",
    "LeadActivityType",
    "LeadAssigneeSummary",
    "LeadAttachmentResponse",
    "LeadBase",
    "LeadContactCreate",
    "LeadContactResponse",
    "LeadCreate",
    "LeadDetailResponse",
    "LeadExterneOrgSummary",
    "LeadMergeRequest",
    "LeadMetricsResponse",
    "LeadMove",
    "LeadNodeCreate",
    "LeadNodeResponse",
    "LeadInitiatiefSummary",
    "LeadParseResult",
    "LeadReorder",
    "LeadResponse",
    "LeadStage",
    "LeadTimelineEvent",
    "LeadTimelineResponse",
    "LeadUpdate",
    # search
    "SearchResponse",
    "SearchResult",
    "SearchResultType",
    "SimilarNodeItem",
    "SimilarNodesResponse",
    # tag
    "LeadTagCreate",
    "LeadTagResponse",
    "NodeTagCreate",
    "NodeTagResponse",
    "TagBase",
    "TagCreate",
    "TagResponse",
    "TagTreeResponse",
    "TagUpdate",
    # mattermost
    "MattermostLinkCodeResponse",
    "MattermostLinkStatusResponse",
    "MattermostUserResponse",
    "MattermostVerifyLinkRequest",
    # mention
    "MentionCreate",
    "MentionReference",
    "MentionResponse",
    "MentionSearchResult",
    # llm
    "CorpusGapOverviewResponse",
    "CorpusGapSummaryItem",
    "EdgeSuggestionItem",
    "GapAnalysisRequest",
    "GapAnalysisResponse",
    "GapItem",
    "KompasGuidanceRequest",
    "KompasGuidanceResponse",
    "TagSuggestionRequest",
    "TagSuggestionResponse",
    # resource_permission
    "ResourcePermissionCreate",
    "ResourcePermissionResponse",
    "ResourcePermissionUpdate",
    # role
    "MyPermissionsResponse",
    "PermissionResponse",
    "PersonRoleCreate",
    "PersonRoleResponse",
    "RoleResponse",
    "RoleWithPermissionsResponse",
    # shared_access
    "SharedAccessCreate",
    "SharedAccessResponse",
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
