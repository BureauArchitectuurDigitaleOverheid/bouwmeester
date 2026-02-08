import { useState, useMemo, useCallback } from 'react';
import { Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
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

// ---- Layout algorithm (simple layered / force-directed) ----

/**
 * Simple hierarchical layout using topological sorting with BFS layers.
 * Nodes with no incoming edges are placed at the top. Edges flow downward.
 * Within each layer, nodes are distributed horizontally.
 */
function computeLayout(
  nodes: CorpusNode[],
  edges: Edge[],
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();

  if (nodes.length === 0) return positions;

  const nodeIds = new Set(nodes.map((n) => n.id));

  // Build adjacency lists
  const inDegree = new Map<string, number>();
  const outEdges = new Map<string, string[]>();
  for (const id of nodeIds) {
    inDegree.set(id, 0);
    outEdges.set(id, []);
  }

  for (const edge of edges) {
    const src = edge.from_node_id;
    const tgt = edge.to_node_id;
    if (nodeIds.has(src) && nodeIds.has(tgt)) {
      inDegree.set(tgt, (inDegree.get(tgt) ?? 0) + 1);
      outEdges.get(src)?.push(tgt);
    }
  }

  // BFS-based layer assignment
  const layers: string[][] = [];
  const assigned = new Set<string>();

  // Start with nodes having in-degree 0
  let currentLayer = [...nodeIds].filter((id) => (inDegree.get(id) ?? 0) === 0);

  // If no roots found (cycle), just pick all nodes
  if (currentLayer.length === 0) {
    currentLayer = [...nodeIds];
  }

  while (currentLayer.length > 0 && assigned.size < nodeIds.size) {
    const layer: string[] = [];
    const nextLayer: string[] = [];

    for (const id of currentLayer) {
      if (!assigned.has(id)) {
        assigned.add(id);
        layer.push(id);

        for (const targetId of outEdges.get(id) ?? []) {
          if (!assigned.has(targetId)) {
            nextLayer.push(targetId);
          }
        }
      }
    }

    if (layer.length > 0) {
      layers.push(layer);
    }
    currentLayer = [...new Set(nextLayer)];
  }

  // Assign any remaining unassigned nodes to the last layer
  const remaining = [...nodeIds].filter((id) => !assigned.has(id));
  if (remaining.length > 0) {
    layers.push(remaining);
  }

  // Build neighbor lookup for barycenter
  const neighbors = new Map<string, Set<string>>();
  for (const id of nodeIds) neighbors.set(id, new Set());
  for (const edge of edges) {
    if (nodeIds.has(edge.from_node_id) && nodeIds.has(edge.to_node_id)) {
      neighbors.get(edge.from_node_id)!.add(edge.to_node_id);
      neighbors.get(edge.to_node_id)!.add(edge.from_node_id);
    }
  }

  // Barycenter crossing reduction: 4 passes (2 down + 2 up)
  const layerPosition = new Map<string, number>();
  for (const layer of layers) {
    layer.forEach((id, idx) => layerPosition.set(id, idx));
  }

  for (let pass = 0; pass < 4; pass++) {
    const forward = pass % 2 === 0;
    const start = forward ? 1 : layers.length - 2;
    const end = forward ? layers.length : -1;
    const step = forward ? 1 : -1;

    for (let i = start; i !== end; i += step) {
      const layer = layers[i];
      const refLayer = layers[i - step];
      const refSet = new Set(refLayer);

      const barycenters = layer.map((id) => {
        const nbrs = [...(neighbors.get(id) ?? [])].filter((n) => refSet.has(n));
        if (nbrs.length === 0) return { id, bc: layerPosition.get(id) ?? 0 };
        const avg = nbrs.reduce((sum, n) => sum + (layerPosition.get(n) ?? 0), 0) / nbrs.length;
        return { id, bc: avg };
      });

      barycenters.sort((a, b) => a.bc - b.bc);
      layers[i] = barycenters.map((b) => b.id);
      layers[i].forEach((id, idx) => layerPosition.set(id, idx));
    }
  }

  // Position nodes
  const nodeWidth = 220;
  const nodeHeight = 80;
  const horizontalGap = 60;
  const verticalGap = 120;

  for (let layerIdx = 0; layerIdx < layers.length; layerIdx++) {
    const layer = layers[layerIdx];
    const layerWidth = layer.length * nodeWidth + (layer.length - 1) * horizontalGap;
    const startX = -layerWidth / 2;

    for (let nodeIdx = 0; nodeIdx < layer.length; nodeIdx++) {
      const nodeId = layer[nodeIdx];
      positions.set(nodeId, {
        x: startX + nodeIdx * (nodeWidth + horizontalGap),
        y: (layers.length - 1 - layerIdx) * (nodeHeight + verticalGap),
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

    // Map normal edges to React Flow edges
    const rfNormalEdges: RFEdge[] = visibleEdges.map((edge) => {
      const isDashed = DASHED_EDGE_TYPES.has(edge.edge_type_id);

      return {
        id: edge.id,
        source: edge.from_node_id,
        target: edge.to_node_id,
        label: vocabEdgeLabel(edge.edge_type_id),
        type: 'default',
        animated: isDashed,
        style: {
          stroke: isDashed ? '#F43F5E' : '#94a3b8',
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
    const rfBridgeEdges: RFEdge[] = bridgeEdges.map((bridge: BridgeEdge) => ({
      id: bridge.id,
      source: bridge.from_node_id,
      target: bridge.to_node_id,
      label: `via ${bridge.bridgedThrough.length} node(s)`,
      type: 'default',
      animated: false,
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
    }));

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
            type: 'default',
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
