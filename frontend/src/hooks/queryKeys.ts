/**
 * Centralized query key definitions for React Query.
 *
 * Using a factory avoids typos and makes key patterns easy to discover.
 * Prefix keys are useful for broad invalidation (e.g. invalidate all nodes).
 */

import type { ActivityFeedParams, EdgeFilters, ParlementairItemFilters, SearchResultType, TaskFilters } from '@/types';

export const queryKeys = {
  // --- Nodes ---
  nodes: {
    all: ['nodes'] as const,
    lists: () => ['nodes', 'list'] as const,
    list: (nodeType?: string, search?: string) => ['nodes', 'list', nodeType, search] as const,
    details: () => ['nodes', 'detail'] as const,
    detail: (id: string | undefined) => ['nodes', 'detail', id] as const,
    neighbors: (id: string | undefined) => ['nodes', 'detail', id, 'neighbors'] as const,
    stakeholders: (id: string | undefined) => ['nodes', 'detail', id, 'stakeholders'] as const,
    titleHistory: (id: string | undefined) => ['nodes', 'detail', id, 'history', 'titles'] as const,
    statusHistory: (id: string | undefined) => ['nodes', 'detail', id, 'history', 'statuses'] as const,
    parlementairItem: (id: string | undefined) => ['nodes', 'detail', id, 'parlementair-item'] as const,
    bronDetail: (id: string | undefined) => ['nodes', 'detail', id, 'bron-detail'] as const,
    bijlage: (id: string | undefined) => ['nodes', 'detail', id, 'bijlage'] as const,
    graph: (id: string | undefined, depth?: number) => ['nodes', 'detail', id, 'graph', depth] as const,
  },

  // --- Tasks ---
  tasks: {
    all: ['tasks'] as const,
    lists: () => ['tasks', 'list'] as const,
    list: (filters?: TaskFilters) => ['tasks', 'list', filters] as const,
    detail: (id: string | null) => ['tasks', 'detail', id] as const,
    subtasks: (taskId: string | null) => ['tasks', 'detail', taskId, 'subtasks'] as const,
    unassigned: (orgId?: string) => ['tasks', 'list', 'unassigned', orgId] as const,
    eenheidOverview: (orgId: string | null) => ['tasks', 'list', 'eenheid-overview', orgId] as const,
    byPerson: (personId: string | null) => ['tasks', 'list', 'by-person', personId] as const,
    workTypes: () => ['tasks', 'work-types'] as const,
  },

  // --- People ---
  people: {
    all: ['people'] as const,
    detail: (id: string | null) => ['people', id] as const,
    summary: (id: string | null) => ['people', id, 'summary'] as const,
    organisaties: (personId: string | null, actief: boolean) => ['people', personId, 'organisaties', { actief }] as const,
    search: (query: string) => ['people', 'search', query] as const,
  },

  // --- Organisatie ---
  organisatie: {
    all: ['organisatie'] as const,
    tree: () => ['organisatie', 'tree'] as const,
    flat: () => ['organisatie', 'flat'] as const,
    detail: (id: string | null) => ['organisatie', id] as const,
    personen: (id: string | null) => ['organisatie', id, 'personen'] as const,
    personenRecursive: (id: string | null) => ['organisatie', id, 'personen', 'recursive'] as const,
    managedBy: (personId: string | undefined) => ['organisatie', 'managed-by', personId] as const,
  },

  // --- Tags ---
  tags: {
    all: ['tags'] as const,
    list: (params?: { tree?: boolean; search?: string }) => ['tags', params] as const,
    forNode: (nodeId: string) => ['node-tags', nodeId] as const,
  },

  // --- Edges ---
  edges: {
    all: ['edges'] as const,
    list: (filters?: EdgeFilters) => ['edges', filters] as const,
  },

  // --- Edge Types ---
  edgeTypes: {
    all: ['edge-types'] as const,
    valid: (fromNodeType?: string, toNodeType?: string) => ['edge-types', 'valid', fromNodeType, toNodeType] as const,
  },

  // --- Edge Schema Rules ---
  edgeSchemaRules: {
    all: ['edge-schema-rules'] as const,
  },

  // --- Notifications ---
  notifications: {
    all: ['notifications'] as const,
    list: (personId: string | undefined, unreadOnly: boolean) => ['notifications', personId, unreadOnly] as const,
    detail: (id: string | undefined, personId?: string) => ['notifications', 'detail', id, personId] as const,
    count: (personId: string | undefined) => ['notifications', 'count', personId] as const,
    replies: (notificationId: string | undefined, personId?: string) => ['notifications', 'replies', notificationId, personId] as const,
  },

  // --- Parlementair ---
  parlementair: {
    all: ['parlementair-items'] as const,
    list: (filters?: ParlementairItemFilters) => ['parlementair-items', filters] as const,
    detail: (id: string) => ['parlementair-items', id] as const,
    reviewQueue: () => ['parlementair-review-queue'] as const,
  },

  // --- Admin ---
  admin: {
    whitelist: () => ['admin', 'whitelist'] as const,
    users: () => ['admin', 'users'] as const,
    accessRequestsAll: () => ['admin', 'access-requests'] as const,
    accessRequests: (status?: string) => ['admin', 'access-requests', status] as const,
    config: () => ['admin', 'config'] as const,
  },

  // --- Activity ---
  activityFeed: (params?: ActivityFeedParams) => ['activity-feed', params] as const,

  // --- Dashboard ---
  dashboardStats: (personId: string | undefined) => ['dashboard-stats', personId] as const,

  // --- Graph ---
  graph: {
    all: ['graph'] as const,
    view: (nodeTypes?: string[], limit?: number) => ['graph', nodeTypes, limit] as const,
  },

  // --- Search ---
  search: (query: string, resultTypes?: SearchResultType[]) => ['search', query, resultTypes] as const,

  // --- Mentions ---
  mentions: {
    references: (targetId: string | undefined) => ['mentions', 'references', targetId] as const,
  },

  // --- Mattermost ---
  mattermost: {
    all: ['mattermost'] as const,
    linkStatus: ['mattermost', 'link-status'] as const,
  },
} as const;
