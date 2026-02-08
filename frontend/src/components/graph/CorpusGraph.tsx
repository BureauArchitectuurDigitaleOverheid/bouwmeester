import { useState, useMemo, useCallback } from 'react';
import { Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  MarkerType,
  useNodesState,
  useEdgesState,
  type Node as RFNode,
  type Edge as RFEdge,
  type Connection,
} from 'reactflow';
import 'reactflow/dist/style.css';

import { GraphNode, type GraphNodeData } from './GraphNode';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { MultiSelect } from '@/components/common/MultiSelect';
import type { MultiSelectOption } from '@/components/common/MultiSelect';
import { useGraphView } from '@/hooks/useGraph';
import { useCreateEdge } from '@/hooks/useEdges';
import { useCreateNode } from '@/hooks/useNodes';
import { NodeType } from '@/types';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { EDGE_TYPE_VOCABULARY } from '@/vocabulary';
import type { CorpusNode, Edge } from '@/types';
import type { SelectOption } from '@/components/common/CreatableSelect';
import { generateBridgeEdges, type BridgeEdge } from '@/utils/bridgeEdges';

// Edge type options are built dynamically in the component using vocabulary

// ---- Layout algorithm using dagre ----

import dagre from 'dagre';

/**
 * Conceptual rank for each node type. Lower rank = higher on screen.
 * Problemen & politieke input at the top, maatregelen & effecten at the bottom.
 */
const NODE_TYPE_RANK: Record<string, number> = {
  [NodeType.PROBLEEM]: 0,
  [NodeType.POLITIEKE_INPUT]: 0,
  [NodeType.DOSSIER]: 1,
  [NodeType.DOEL]: 2,
  [NodeType.BELEIDSKADER]: 2,
  [NodeType.BELEIDSOPTIE]: 3,
  [NodeType.INSTRUMENT]: 4,
  [NodeType.MAATREGEL]: 4,
  [NodeType.EFFECT]: 5,
  [NodeType.NOTITIE]: 3,
  [NodeType.OVERIG]: 3,
};

/**
 * Hierarchical layout using dagre (Sugiyama-style).
 * Edges are oriented for dagre so that nodes with lower conceptual rank
 * (problemen, politieke input) are placed higher. The original edge
 * directions are NOT changed — only dagre sees the reoriented edges.
 * React Flow still draws arrows in the original from→to direction.
 */
function computeLayout(
  nodes: CorpusNode[],
  edges: Edge[],
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();

  if (nodes.length === 0) return positions;

  const nodeIds = new Set(nodes.map((n) => n.id));
  const nodeTypeMap = new Map(nodes.map((n) => [n.id, n.node_type]));

  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir: 'TB',
    nodesep: 40,
    ranksep: 100,
    edgesep: 20,
    marginx: 40,
    marginy: 40,
  });

  for (const node of nodes) {
    g.setNode(node.id, { width: 220, height: 80 });
  }

  // Orient edges for dagre: always point from lower rank (top) to higher rank
  // (bottom). When both endpoints have the same rank, keep original direction.
  for (const edge of edges) {
    if (nodeIds.has(edge.from_node_id) && nodeIds.has(edge.to_node_id)) {
      const fromRank = NODE_TYPE_RANK[nodeTypeMap.get(edge.from_node_id) ?? ''] ?? 3;
      const toRank = NODE_TYPE_RANK[nodeTypeMap.get(edge.to_node_id) ?? ''] ?? 3;
      if (fromRank <= toRank) {
        g.setEdge(edge.from_node_id, edge.to_node_id);
      } else {
        g.setEdge(edge.to_node_id, edge.from_node_id);
      }
    }
  }

  dagre.layout(g);

  for (const node of nodes) {
    const n = g.node(node.id);
    if (n) {
      // dagre returns center positions; React Flow uses top-left
      positions.set(node.id, {
        x: n.x - 110,
        y: n.y - 40,
      });
    }
  }

  return positions;
}

// ---- Node type color map for minimap ----

const NODE_TYPE_HEX_COLORS: Record<string, string> = {
  [NodeType.DOSSIER]: '#3B82F6',
  [NodeType.DOEL]: '#10B981',
  [NodeType.INSTRUMENT]: '#8B5CF6',
  [NodeType.BELEIDSKADER]: '#F59E0B',
  [NodeType.MAATREGEL]: '#06B6D4',
  [NodeType.POLITIEKE_INPUT]: '#F43F5E',
  [NodeType.PROBLEEM]: '#EF4444',
  [NodeType.EFFECT]: '#059669',
  [NodeType.BELEIDSOPTIE]: '#6366F1',
  [NodeType.NOTITIE]: '#64748b',
  [NodeType.OVERIG]: '#9ca3af',
};

// ---- Edge type styling ----

const DASHED_EDGE_TYPES = new Set(['conflicteert_met', 'conflicteert']);

// Node type options are built dynamically in the component using vocabulary

// Custom node types for React Flow
const nodeTypes = {
  corpusNode: GraphNode,
};

export function CorpusGraph() {
  const navigate = useNavigate();
  const { nodeLabel, edgeLabel: vocabEdgeLabel } = useVocabulary();
  const { data, isLoading, error } = useGraphView();

  const edgeTypeOptions: SelectOption[] = Object.keys(EDGE_TYPE_VOCABULARY).map((key) => ({
    value: key,
    label: vocabEdgeLabel(key),
  }));

  const nodeTypeFilterOptions: MultiSelectOption[] = Object.values(NodeType).map((t) => ({
    value: t,
    label: nodeLabel(t),
    color: NODE_TYPE_HEX_COLORS[t],
  }));
  const createEdge = useCreateEdge();

  // Filter state
  const [enabledNodeTypes, setEnabledNodeTypes] = useState<Set<NodeType>>(
    () => new Set(Object.values(NodeType)),
  );
  const [enabledEdgeTypes, setEnabledEdgeTypes] = useState<Set<string>>(new Set());
  const [edgeTypesInitialized, setEdgeTypesInitialized] = useState(false);

  // Edge creation state
  const [pendingConnection, setPendingConnection] = useState<Connection | null>(null);
  const [newEdgeType, setNewEdgeType] = useState('');

  // Node creation state
  const createNodeMutation = useCreateNode();
  const [showCreateNode, setShowCreateNode] = useState(false);
  const [newNodeTitle, setNewNodeTitle] = useState('');
  const [newNodeType, setNewNodeType] = useState('');
  const [newNodeDescription, setNewNodeDescription] = useState('');

  // Extract available edge types from data
  const availableEdgeTypes = useMemo(() => {
    if (!data?.edges) return [];
    const types = new Set<string>();
    for (const edge of data.edges) {
      if (edge.edge_type_id) types.add(edge.edge_type_id);
    }
    return [...types].sort();
  }, [data?.edges]);

  // Initialize edge type filter once data is available
  if (availableEdgeTypes.length > 0 && !edgeTypesInitialized) {
    setEnabledEdgeTypes(new Set(availableEdgeTypes));
    setEdgeTypesInitialized(true);
  }

  // Build React Flow nodes and edges
  const { rfNodes, rfEdges } = useMemo(() => {
    if (!data?.nodes || !data?.edges) {
      return { rfNodes: [], rfEdges: [] };
    }

    // Filter nodes by enabled types
    const filteredNodes = data.nodes.filter((n) => enabledNodeTypes.has(n.node_type));

    // Filter edges by enabled edge types only (not by visible node endpoints)
    const typeFilteredEdges = data.edges.filter((e) => enabledEdgeTypes.has(e.edge_type_id));

    // Generate bridge edges for nodes hidden by the node-type filter
    const { visibleEdges, bridgeEdges } = generateBridgeEdges(
      data.nodes,
      typeFilteredEdges,
      filteredNodes,
    );

    // Compute layout using only the direct visible edges
    const positions = computeLayout(filteredNodes, visibleEdges);

    // Map to React Flow nodes
    const rfNodes: RFNode<GraphNodeData>[] = filteredNodes.map((node) => {
      const pos = positions.get(node.id) ?? { x: 0, y: 0 };
      return {
        id: node.id,
        type: 'corpusNode',
        position: pos,
        data: {
          label: node.title,
          nodeType: node.node_type,
          onClick: () => navigate(`/nodes/${node.id}`),
        },
      };
    });

    // Map normal edges to React Flow edges.
    // When the source is placed below the target by dagre, we swap
    // source/target for React Flow routing and use markerStart so the
    // arrow still points in the original semantic direction.
    const rfNormalEdges: RFEdge[] = visibleEdges.map((edge) => {
      const isDashed = DASHED_EDGE_TYPES.has(edge.edge_type_id);
      const fromPos = positions.get(edge.from_node_id);
      const toPos = positions.get(edge.to_node_id);
      const goesUpward = fromPos && toPos && fromPos.y > toPos.y;
      const color = isDashed ? '#F43F5E' : '#94a3b8';
      const marker = { type: MarkerType.ArrowClosed, width: 16, height: 16, color };

      return {
        id: edge.id,
        source: goesUpward ? edge.to_node_id : edge.from_node_id,
        target: goesUpward ? edge.from_node_id : edge.to_node_id,
        label: vocabEdgeLabel(edge.edge_type_id),
        type: 'bezier',
        animated: isDashed,
        ...(goesUpward
          ? { markerStart: marker }
          : { markerEnd: marker }),
        style: {
          stroke: color,
          strokeWidth: 1.5,
          strokeDasharray: isDashed ? '5 5' : undefined,
        },
        labelStyle: {
          fontSize: 10,
          fill: '#64748b',
          fontWeight: 500,
        },
        labelBgStyle: {
          fill: '#ffffff',
          fillOpacity: 0.9,
        },
        labelBgPadding: [4, 2] as [number, number],
        labelBgBorderRadius: 4,
      };
    });

    // Map bridge edges to React Flow edges with dashed bridge styling
    const rfBridgeEdges: RFEdge[] = bridgeEdges.map((bridge: BridgeEdge) => {
      const fromPos = positions.get(bridge.from_node_id);
      const toPos = positions.get(bridge.to_node_id);
      const goesUp = fromPos && toPos && fromPos.y > toPos.y;
      const bMarker = { type: MarkerType.ArrowClosed, width: 14, height: 14, color: '#94a3b8' };
      return {
      id: bridge.id,
      source: goesUp ? bridge.to_node_id : bridge.from_node_id,
      target: goesUp ? bridge.from_node_id : bridge.to_node_id,
      label: `via ${bridge.bridgedThrough.length} node(s)`,
      type: 'bezier',
      animated: false,
      ...(goesUp ? { markerStart: bMarker } : { markerEnd: bMarker }),
      style: {
        stroke: '#94a3b8',
        strokeWidth: 1.5,
        strokeDasharray: '3 3',
        opacity: 0.6,
      },
      labelStyle: {
        fontSize: 9,
        fill: '#94a3b8',
        fontStyle: 'italic',
        fontWeight: 400,
      },
      labelBgStyle: {
        fill: '#ffffff',
        fillOpacity: 0.9,
      },
      labelBgPadding: [4, 2] as [number, number],
      labelBgBorderRadius: 4,
    };
    });

    const rfEdges: RFEdge[] = [...rfNormalEdges, ...rfBridgeEdges];

    return { rfNodes, rfEdges };
  }, [data, enabledNodeTypes, enabledEdgeTypes, navigate, vocabEdgeLabel]);

  // React Flow state
  const [nodes, setNodes, onNodesChange] = useNodesState(rfNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(rfEdges);

  // Sync rfNodes/rfEdges into state when they change
  useMemo(() => {
    setNodes(rfNodes);
    setEdges(rfEdges);
  }, [rfNodes, rfEdges, setNodes, setEdges]);

  // Edge type options for multi-select (derived from data)
  const edgeTypeFilterOptions: MultiSelectOption[] = useMemo(
    () => availableEdgeTypes.map((t) => ({ value: t, label: vocabEdgeLabel(t) })),
    [availableEdgeTypes, vocabEdgeLabel],
  );

  // Wrap Set onChange for node types to cast correctly
  const handleNodeTypesChange = useCallback((next: Set<string>) => {
    setEnabledNodeTypes(next as Set<NodeType>);
  }, []);

  // Handle connection drag completion
  const handleConnect = useCallback((connection: Connection) => {
    if (connection.source && connection.target) {
      setPendingConnection(connection);
      setNewEdgeType('');
    }
  }, []);

  const handleCreateEdge = useCallback(async () => {
    if (!pendingConnection?.source || !pendingConnection?.target || !newEdgeType) return;
    await createEdge.mutateAsync({
      from_node_id: pendingConnection.source,
      to_node_id: pendingConnection.target,
      edge_type_id: newEdgeType,
    });
    setPendingConnection(null);
    setNewEdgeType('');
  }, [pendingConnection, newEdgeType, createEdge]);

  // Node type options for create modal
  const nodeTypeCreateOptions: SelectOption[] = Object.values(NodeType).map((t) => ({
    value: t,
    label: nodeLabel(t),
  }));

  const handleOpenCreateNode = useCallback(() => {
    setNewNodeTitle('');
    setNewNodeType('');
    setNewNodeDescription('');
    setShowCreateNode(true);
  }, []);

  const handleCreateNode = useCallback(async () => {
    if (!newNodeTitle.trim() || !newNodeType) return;
    await createNodeMutation.mutateAsync({
      title: newNodeTitle.trim(),
      node_type: newNodeType as NodeType,
      description: newNodeDescription.trim() || undefined,
    });
    setShowCreateNode(false);
  }, [newNodeTitle, newNodeType, newNodeDescription, createNodeMutation]);

  // Minimap node color
  const minimapNodeColor = useCallback((node: RFNode) => {
    const nodeType = (node.data as GraphNodeData)?.nodeType;
    return NODE_TYPE_HEX_COLORS[nodeType] ?? '#9ca3af';
  }, []);

  if (isLoading) {
    return <LoadingSpinner className="py-12" />;
  }

  if (error) {
    return (
      <EmptyState
        title="Fout bij laden"
        description="Er is een fout opgetreden bij het laden van de grafiek. Probeer het opnieuw."
      />
    );
  }

  if (!data?.nodes?.length) {
    return (
      <EmptyState
        title="Geen nodes gevonden"
        description="Er zijn nog geen nodes in het corpus. Maak een nieuwe node aan."
      />
    );
  }

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="w-52">
          <MultiSelect
            value={enabledNodeTypes as Set<string>}
            onChange={handleNodeTypesChange}
            options={nodeTypeFilterOptions}
            allLabel="Alle types"
          />
        </div>
        {edgeTypeFilterOptions.length > 0 && (
          <div className="w-52">
            <MultiSelect
              value={enabledEdgeTypes}
              onChange={setEnabledEdgeTypes}
              options={edgeTypeFilterOptions}
              allLabel="Alle relaties"
            />
          </div>
        )}
        <Button onClick={handleOpenCreateNode} size="sm">
          <Plus className="h-4 w-4 mr-1" />
          Node toevoegen
        </Button>
      </div>

      {/* Graph canvas */}
      <div className="bg-white rounded-xl border border-border shadow-sm overflow-hidden" style={{ height: 'calc(100vh - 260px)', minHeight: '500px' }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={handleConnect}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.2, maxZoom: 1.5 }}
          minZoom={0.1}
          maxZoom={3}
          defaultEdgeOptions={{
            type: 'bezier',
          }}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#e2e8f0" gap={20} size={1} />
          <Controls
            showInteractive={false}
            style={{
              borderRadius: '10px',
              border: '1px solid #e2e8f0',
              boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
            }}
          />
          <MiniMap
            nodeColor={minimapNodeColor}
            maskColor="rgba(248, 249, 250, 0.7)"
            style={{
              borderRadius: '10px',
              border: '1px solid #e2e8f0',
              boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
            }}
          />
        </ReactFlow>
      </div>

      {/* Edge type picker modal after drag-connect */}
      <Modal
        open={!!pendingConnection}
        onClose={() => setPendingConnection(null)}
        title="Verbinding aanmaken"
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setPendingConnection(null)}>
              Annuleren
            </Button>
            <Button
              onClick={handleCreateEdge}
              loading={createEdge.isPending}
              disabled={!newEdgeType}
            >
              Toevoegen
            </Button>
          </>
        }
      >
        <CreatableSelect
          label="Type verbinding"
          value={newEdgeType}
          onChange={setNewEdgeType}
          options={edgeTypeOptions}
          placeholder="Selecteer een type..."
          required
        />
      </Modal>

      {/* Create node modal */}
      <Modal
        open={showCreateNode}
        onClose={() => setShowCreateNode(false)}
        title="Nieuwe node aanmaken"
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowCreateNode(false)}>
              Annuleren
            </Button>
            <Button
              onClick={handleCreateNode}
              loading={createNodeMutation.isPending}
              disabled={!newNodeTitle.trim() || !newNodeType}
            >
              Aanmaken
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label="Titel"
            value={newNodeTitle}
            onChange={(e) => setNewNodeTitle(e.target.value)}
            placeholder="Naam van de node..."
            required
          />
          <CreatableSelect
            label="Type"
            value={newNodeType}
            onChange={setNewNodeType}
            options={nodeTypeCreateOptions}
            placeholder="Selecteer een type..."
            required
          />
          <div className="space-y-1.5">
            <label className="block text-sm font-medium text-text">Beschrijving</label>
            <textarea
              className="block w-full rounded-xl border border-border bg-white px-3.5 py-2.5 text-sm text-text placeholder:text-text-secondary/50 transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 hover:border-border-hover"
              value={newNodeDescription}
              onChange={(e) => setNewNodeDescription(e.target.value)}
              placeholder="Optionele beschrijving..."
              rows={3}
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}
