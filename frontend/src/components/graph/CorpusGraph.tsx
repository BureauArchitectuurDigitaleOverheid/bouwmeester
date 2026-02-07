import { useState, useMemo, useCallback } from 'react';
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
import { GraphFilters } from './GraphFilters';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { useGraphView } from '@/hooks/useGraph';
import { useCreateEdge } from '@/hooks/useEdges';
import { NodeType } from '@/types';
import type { CorpusNode, Edge } from '@/types';
import type { SelectOption } from '@/components/common/CreatableSelect';

const edgeTypeOptions: SelectOption[] = [
  { value: 'kadert', label: 'Kadert in' },
  { value: 'draagt_bij_aan', label: 'Draagt bij aan' },
  { value: 'implementeert', label: 'Implementeert' },
  { value: 'vereist', label: 'Vereist' },
  { value: 'aanvulling_op', label: 'Aanvulling op' },
  { value: 'conflicteert_met', label: 'Conflicteert met' },
  { value: 'vervangt', label: 'Vervangt' },
];

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
    const src = edge.source_id ?? (edge as Record<string, unknown>).from_node_id as string;
    const tgt = edge.target_id ?? (edge as Record<string, unknown>).to_node_id as string;
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
        y: layerIdx * (nodeHeight + verticalGap),
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
  [NodeType.NOTITIE]: '#64748b',
  [NodeType.OVERIG]: '#9ca3af',
};

// ---- Edge type styling ----

const DASHED_EDGE_TYPES = new Set(['conflicteert_met', 'conflicteert']);

// Custom node types for React Flow
const nodeTypes = {
  corpusNode: GraphNode,
};

export function CorpusGraph() {
  const navigate = useNavigate();
  const { data, isLoading, error } = useGraphView();
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

  // Extract available edge types from data
  const availableEdgeTypes = useMemo(() => {
    if (!data?.edges) return [];
    const types = new Set<string>();
    for (const edge of data.edges) {
      const edgeType = edge.edge_type ?? (edge as Record<string, unknown>).edge_type_id as string;
      if (edgeType) types.add(edgeType);
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
    const filteredNodeIds = new Set(filteredNodes.map((n) => n.id));

    // Filter edges: both endpoints must be visible, and edge type must be enabled
    const filteredEdges = data.edges.filter((e) => {
      const src = e.source_id ?? (e as Record<string, unknown>).from_node_id as string;
      const tgt = e.target_id ?? (e as Record<string, unknown>).to_node_id as string;
      const edgeType = e.edge_type ?? (e as Record<string, unknown>).edge_type_id as string;
      return (
        filteredNodeIds.has(src) &&
        filteredNodeIds.has(tgt) &&
        enabledEdgeTypes.has(edgeType)
      );
    });

    // Compute layout
    const positions = computeLayout(filteredNodes, filteredEdges);

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

    // Map to React Flow edges
    const rfEdges: RFEdge[] = filteredEdges.map((edge) => {
      const src = edge.source_id ?? (edge as Record<string, unknown>).from_node_id as string;
      const tgt = edge.target_id ?? (edge as Record<string, unknown>).to_node_id as string;
      const edgeType = edge.edge_type ?? (edge as Record<string, unknown>).edge_type_id as string;
      const isDashed = DASHED_EDGE_TYPES.has(edgeType);

      return {
        id: edge.id,
        source: src,
        target: tgt,
        label: edgeType?.replace(/_/g, ' '),
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

    return { rfNodes, rfEdges };
  }, [data, enabledNodeTypes, enabledEdgeTypes, navigate]);

  // React Flow state
  const [nodes, setNodes, onNodesChange] = useNodesState(rfNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(rfEdges);

  // Sync rfNodes/rfEdges into state when they change
  useMemo(() => {
    setNodes(rfNodes);
    setEdges(rfEdges);
  }, [rfNodes, rfEdges, setNodes, setEdges]);

  // Toggle handlers
  const handleToggleNodeType = useCallback((type: NodeType) => {
    setEnabledNodeTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  }, []);

  const handleToggleEdgeType = useCallback((type: string) => {
    setEnabledEdgeTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  }, []);

  const handleSelectAllNodeTypes = useCallback(() => {
    setEnabledNodeTypes(new Set(Object.values(NodeType)));
  }, []);

  const handleDeselectAllNodeTypes = useCallback(() => {
    setEnabledNodeTypes(new Set());
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
    <div className="flex gap-4" style={{ height: 'calc(100vh - 200px)', minHeight: '500px' }}>
      {/* Filter sidebar */}
      <div className="w-56 shrink-0 overflow-y-auto">
        <GraphFilters
          enabledNodeTypes={enabledNodeTypes}
          onToggleNodeType={handleToggleNodeType}
          enabledEdgeTypes={enabledEdgeTypes}
          availableEdgeTypes={availableEdgeTypes}
          onToggleEdgeType={handleToggleEdgeType}
          onSelectAllNodeTypes={handleSelectAllNodeTypes}
          onDeselectAllNodeTypes={handleDeselectAllNodeTypes}
        />
      </div>

      {/* Graph canvas */}
      <div className="flex-1 bg-white rounded-xl border border-border shadow-sm overflow-hidden">
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
    </div>
  );
}
