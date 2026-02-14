import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useIsMobile } from '@/hooks/useMediaQuery';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  MarkerType,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
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
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { useGraphView } from '@/hooks/useGraph';
import { useCreateEdge } from '@/hooks/useEdges';
import { NodeType, NODE_TYPE_HEX_COLORS } from '@/types';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { EDGE_TYPE_VOCABULARY } from '@/vocabulary';
import type { CorpusNode, Edge } from '@/types';
import type { SelectOption } from '@/components/common/CreatableSelect';
import { generateBridgeEdges, type BridgeEdge } from '@/utils/bridgeEdges';

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
  [NodeType.BRON]: 3,
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
      positions.set(node.id, {
        x: n.x - 110,
        y: n.y - 40,
      });
    }
  }

  return positions;
}

// ---- Edge type styling ----

const DASHED_EDGE_TYPES = new Set(['conflicteert_met', 'conflicteert']);

// Custom node types for React Flow
const nodeTypes = {
  corpusNode: GraphNode,
};

interface CorpusGraphProps {
  enabledNodeTypes: Set<NodeType>;
  searchQuery: string;
  enabledEdgeTypes: Set<string>;
}

// Inner component that uses useReactFlow (must be inside ReactFlowProvider)
function CorpusGraphInner({ enabledNodeTypes, searchQuery, enabledEdgeTypes }: CorpusGraphProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const isMobile = useIsMobile();
  const { edgeLabel: vocabEdgeLabel } = useVocabulary();
  const { data, isLoading, error } = useGraphView();
  const reactFlowInstance = useReactFlow();

  // Stable refs for callbacks used inside the layout memo, so they don't
  // cause the expensive dagre layout to recompute.
  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;
  const locationRef = useRef(location);
  locationRef.current = location;
  const vocabEdgeLabelRef = useRef(vocabEdgeLabel);
  vocabEdgeLabelRef.current = vocabEdgeLabel;

  const edgeTypeOptions: SelectOption[] = Object.keys(EDGE_TYPE_VOCABULARY).map((key) => ({
    value: key,
    label: vocabEdgeLabel(key),
  }));

  const createEdge = useCreateEdge();

  // Edge creation state
  const [pendingConnection, setPendingConnection] = useState<Connection | null>(null);
  const [newEdgeType, setNewEdgeType] = useState('');

  // ---- Step 1: Compute stable layout with ALL nodes and edges ----
  // Only recomputes when the underlying data changes, NOT when filters change.
  // Uses refs for navigate/vocabEdgeLabel to keep deps stable.
  const { allRfNodes, allRfEdges } = useMemo(() => {
    if (!data?.nodes || !data?.edges) {
      return { allRfNodes: [], allRfEdges: [] };
    }

    const positions = computeLayout(data.nodes, data.edges);

    const allRfNodes: RFNode<GraphNodeData>[] = data.nodes.map((node) => {
      const pos = positions.get(node.id) ?? { x: 0, y: 0 };
      return {
        id: node.id,
        type: 'corpusNode',
        position: pos,
        data: {
          label: node.title,
          description: node.description,
          nodeType: node.node_type,
          onClick: () => navigateRef.current(`/nodes/${node.id}`, { state: { fromCorpus: locationRef.current.pathname + locationRef.current.search } }),
        },
      };
    });

    const allRfEdges: RFEdge[] = data.edges.map((edge) => {
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
        label: vocabEdgeLabelRef.current(edge.edge_type_id),
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

    return { allRfNodes, allRfEdges };
  }, [data]);

  // Build a lookup from RF edge id → original edge_type_id for fast filtering
  const edgeTypeById = useMemo(() => {
    const map = new Map<string, string>();
    if (data?.edges) {
      for (const e of data.edges) map.set(e.id, e.edge_type_id);
    }
    return map;
  }, [data?.edges]);

  // ---- Step 2: Apply filters as visibility + generate bridge edges ----
  // Positions stay the same; hidden nodes disappear in place.
  // Bridge edges connect visible neighbours of hidden nodes.
  const { rfNodes, rfEdges } = useMemo(() => {
    const q = searchQuery.toLowerCase();

    // Determine which node IDs are visible
    const visibleNodeIds = new Set<string>();
    const rfNodes = allRfNodes.map((node) => {
      const nodeData = node.data as GraphNodeData;
      const matchesType = enabledNodeTypes.has(nodeData.nodeType as NodeType);
      const matchesSearch = !q
        || nodeData.label.toLowerCase().includes(q)
        || nodeData.description?.toLowerCase().includes(q);
      const isVisible = matchesType && matchesSearch;
      if (isVisible) visibleNodeIds.add(node.id);
      return { ...node, hidden: !isVisible };
    });

    // Hide edges where either endpoint is hidden or edge type is filtered out
    const filteredRfEdges = allRfEdges.map((edge) => {
      const edgeType = edgeTypeById.get(edge.id);
      const edgeTypeMatch = edgeType ? enabledEdgeTypes.has(edgeType) : true;
      const bothEndpointsVisible = visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target);
      return { ...edge, hidden: !edgeTypeMatch || !bothEndpointsVisible };
    });

    // Generate bridge edges for hidden nodes that connect visible nodes
    if (data?.nodes && data?.edges) {
      const visibleNodes = data.nodes.filter((n) => visibleNodeIds.has(n.id));
      const edgeTypeFilteredEdges = data.edges.filter((e) => enabledEdgeTypes.has(e.edge_type_id));
      const { bridgeEdges } = generateBridgeEdges(data.nodes, edgeTypeFilteredEdges, visibleNodes);

      // Find positions from the allRfNodes (which have stable layout positions)
      const positionMap = new Map(allRfNodes.map((n) => [n.id, n.position]));

      const rfBridgeEdges: RFEdge[] = bridgeEdges.map((bridge: BridgeEdge) => {
        const fromPos = positionMap.get(bridge.from_node_id);
        const toPos = positionMap.get(bridge.to_node_id);
        const goesUp = fromPos && toPos && fromPos.y > toPos.y;
        const bMarker = { type: MarkerType.ArrowClosed, width: 14, height: 14, color: '#94a3b8' };
        return {
          id: bridge.id,
          source: goesUp ? bridge.to_node_id : bridge.from_node_id,
          target: goesUp ? bridge.from_node_id : bridge.to_node_id,
          label: `via ${bridge.bridgedThrough.length} nodes`,
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

      return { rfNodes, rfEdges: [...filteredRfEdges, ...rfBridgeEdges] };
    }

    return { rfNodes, rfEdges: filteredRfEdges };
  }, [allRfNodes, allRfEdges, edgeTypeById, enabledNodeTypes, enabledEdgeTypes, searchQuery, data]);

  // React Flow state
  const [nodes, setNodes, onNodesChange] = useNodesState(rfNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(rfEdges);

  // Sync rfNodes/rfEdges into state when they change
  useEffect(() => {
    setNodes(rfNodes);
    setEdges(rfEdges);
  }, [rfNodes, rfEdges, setNodes, setEdges]);

  // Re-fit viewport when filters change (skip initial render — ReactFlow's
  // fitView prop handles that).
  const isInitialRender = useRef(true);
  useEffect(() => {
    if (isInitialRender.current) {
      isInitialRender.current = false;
      return;
    }
    const timer = setTimeout(() => {
      reactFlowInstance.fitView({ padding: 0.2, maxZoom: 1.5, duration: 300 });
    }, 50);
    return () => clearTimeout(timer);
  }, [rfNodes, rfEdges, reactFlowInstance]);

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
    <div className="space-y-4">
      {/* Graph canvas */}
      <div className="bg-white rounded-xl border border-border shadow-sm overflow-hidden" style={{ height: 'calc(100vh - 260px)', minHeight: isMobile ? '300px' : '500px' }}>
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
          {!isMobile && (
            <MiniMap
              nodeColor={minimapNodeColor}
              maskColor="rgba(248, 249, 250, 0.7)"
              style={{
                borderRadius: '10px',
                border: '1px solid #e2e8f0',
                boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
              }}
            />
          )}
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

// Wrap in ReactFlowProvider so useReactFlow() works
export function CorpusGraph(props: CorpusGraphProps) {
  return (
    <ReactFlowProvider>
      <CorpusGraphInner {...props} />
    </ReactFlowProvider>
  );
}
