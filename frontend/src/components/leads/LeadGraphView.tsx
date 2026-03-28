import { useState, useMemo, useCallback, useEffect, useRef, memo } from 'react';
import { Building2, User, FileText, Lightbulb, Plus } from 'lucide-react';
import { useIsMobile } from '@/hooks/useMediaQuery';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  MarkerType,
  useNodesState,
  useEdgesState,
  ReactFlowProvider,
  Handle,
  Position,
  type Node as RFNode,
  type Edge as RFEdge,
  type NodeProps,
  type Connection,
} from 'reactflow';
import 'reactflow/dist/style.css';
import dagre from 'dagre';

import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { LeadMetricsBar } from './LeadMetricsBar';
import { CommunityEdgeModal } from './CommunityEdgeModal';
import { AddLeadContactModal } from './AddLeadContactModal';
import { useCommunityGraph } from '@/hooks/useLeads';
import { useLeadDetail } from '@/contexts/LeadDetailContext';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import {
  LeadStage,
  LEAD_STAGE_LABELS,
  LEAD_STAGE_COLORS,
  NODE_TYPE_HEX_COLORS,
  NodeType,
  formatFunctie,
} from '@/types';
import type { CommunityGraphNode, CommunityGraphEdge } from '@/types';

// ---- Hex colors per lead stage (for graph nodes) ----
const LEAD_STAGE_HEX: Record<string, string> = {
  verkennen: '#60A5FA',
  eerste_gesprek: '#FBBF24',
  interne_check: '#FB923C',
  follow_up: '#A78BFA',
  in_the_pocket: '#34D399',
  koelkast: '#9CA3AF',
};

const PERSON_COLOR = '#EC4899';
const ORG_COLOR = '#14B8A6';
const CORPUS_NODE_FALLBACK = '#6B7280';

// ---- Community node type to rank (dagre) ----
const COMMUNITY_NODE_RANK: Record<string, number> = {
  organisation: 0,
  corpus_node: 1,
  lead: 2,
  person: 3,
};

// ---- Edge type styling ----
interface EdgeStyle {
  color: string;
  strokeDasharray?: string;
  strokeWidth: number;
  animated?: boolean;
  label: string;
}

function edgeStyle(edgeType: string): EdgeStyle {
  switch (edgeType) {
    case 'verantwoordelijke':
      return { color: '#3B82F6', strokeWidth: 1.5, label: 'verantwoordelijk' };
    case 'contact':
      return { color: '#10B981', strokeDasharray: '5 5', strokeWidth: 1.5, label: 'contact' };
    case 'organisatie':
      return { color: '#14B8A6', strokeWidth: 1.5, label: 'organisatie' };
    case 'gelinkt':
      return { color: '#6B7280', strokeWidth: 1.5, label: 'gelinkt' };
    case 'eigenaar':
    case 'betrokken':
    case 'adviseur':
      return { color: '#8B5CF6', strokeDasharray: '2 4', strokeWidth: 1.5, label: edgeType };
    case 'lid_van':
      return { color: '#9CA3AF', strokeWidth: 1, label: 'lid van' };
    default:
      // Corpus node edges and anything else
      return { color: '#94a3b8', strokeWidth: 1.5, label: edgeType.replace(/_/g, ' ') };
  }
}

// ---- Custom node component ----
type CommunityNodeType = 'lead' | 'person' | 'organisation' | 'corpus_node';

interface CommunityGraphNodeData {
  label: string;
  nodeType: CommunityNodeType;
  stage?: string | null;
  initiatiefId?: string | null;
  functie?: string | null;
  orgType?: string | null;
  corpusNodeType?: string | null;
  onClick?: () => void;
  onAddContact?: () => void;
}

function getNodeColor(data: CommunityGraphNodeData): string {
  if (data.nodeType === 'lead') {
    return LEAD_STAGE_HEX[data.stage ?? ''] ?? '#9CA3AF';
  }
  if (data.nodeType === 'person') return PERSON_COLOR;
  if (data.nodeType === 'organisation') return ORG_COLOR;
  if (data.nodeType === 'corpus_node' && data.corpusNodeType) {
    return NODE_TYPE_HEX_COLORS[data.corpusNodeType as NodeType] ?? CORPUS_NODE_FALLBACK;
  }
  return CORPUS_NODE_FALLBACK;
}

function CommunityGraphNodeComponent({ data }: NodeProps<CommunityGraphNodeData>) {
  const color = getNodeColor(data);

  const badgeContent = (() => {
    if (data.nodeType === 'lead' && data.stage) {
      const stageKey = data.stage as LeadStage;
      return (
        <span
          className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-medium mb-1 ${LEAD_STAGE_COLORS[stageKey] ?? 'bg-gray-100 text-gray-800'}`}
        >
          {LEAD_STAGE_LABELS[stageKey] ?? data.stage}
        </span>
      );
    }
    if (data.nodeType === 'person') {
      return (
        <div className="flex items-center gap-1 mb-1">
          <User className="h-3 w-3" style={{ color }} />
          <span style={{ color, fontSize: '10px', fontWeight: 600, letterSpacing: '0.025em', textTransform: 'uppercase' }}>
            {formatFunctie(data.functie) ?? 'Persoon'}
          </span>
        </div>
      );
    }
    if (data.nodeType === 'organisation') {
      return (
        <div className="flex items-center gap-1 mb-1">
          <Building2 className="h-3 w-3" style={{ color }} />
          <span style={{ color, fontSize: '10px', fontWeight: 600, letterSpacing: '0.025em', textTransform: 'uppercase' }}>
            {data.orgType ?? 'Organisatie'}
          </span>
        </div>
      );
    }
    if (data.nodeType === 'corpus_node') {
      return (
        <div className="flex items-center gap-1 mb-1">
          <FileText className="h-3 w-3" style={{ color }} />
          <span style={{ color, fontSize: '10px', fontWeight: 600, letterSpacing: '0.025em', textTransform: 'uppercase' }}>
            {data.corpusNodeType?.replace(/_/g, ' ') ?? 'Node'}
          </span>
        </div>
      );
    }
    return null;
  })();

  return (
    <div
      onClick={data.onClick}
      style={{
        background: '#ffffff',
        borderRadius: '10px',
        boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px -1px rgba(0, 0, 0, 0.1)',
        border: `1px solid ${color}33`,
        minWidth: '160px',
        maxWidth: '220px',
        cursor: data.onClick ? 'pointer' : 'default',
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      <div style={{ height: '4px', background: color, borderRadius: '10px 10px 0 0' }} />
      <div style={{ padding: '8px 12px', paddingBottom: data.onAddContact ? '28px' : '8px' }}>
        {badgeContent}
        <div
          style={{
            fontSize: '13px',
            fontWeight: 500,
            color: '#1A1A2E',
            lineHeight: '1.4',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
          }}
        >
          {data.label}
        </div>
      </div>
      {data.onAddContact && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            data.onAddContact?.();
          }}
          title="Contact toevoegen"
          style={{
            position: 'absolute',
            bottom: '6px',
            right: '6px',
            width: '20px',
            height: '20px',
            borderRadius: '50%',
            background: color,
            color: '#fff',
            border: 'none',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            opacity: 0.8,
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.opacity = '1';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.opacity = '0.8';
          }}
        >
          <Plus style={{ width: '12px', height: '12px' }} />
        </button>
      )}
      <Handle
        type="target"
        position={Position.Top}
        style={{ width: '8px', height: '8px', background: color, border: '2px solid white', top: '-4px' }}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        style={{ width: '8px', height: '8px', background: color, border: '2px solid white', bottom: '-4px' }}
      />
    </div>
  );
}

const CommunityGraphNodeMemo = memo(CommunityGraphNodeComponent);
const nodeTypes = { communityNode: CommunityGraphNodeMemo };

// ---- Dagre layout ----
function computeLayout(
  nodes: CommunityGraphNode[],
  edges: CommunityGraphEdge[],
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();
  if (nodes.length === 0) return positions;

  const nodeIds = new Set(nodes.map((n) => n.id));
  const nodeTypeMap = new Map(nodes.map((n) => [n.id, n.node_type]));

  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir: 'TB',
    nodesep: 50,
    ranksep: 120,
    edgesep: 20,
    marginx: 40,
    marginy: 40,
  });

  for (const node of nodes) {
    g.setNode(node.id, { width: 200, height: 80 });
  }

  for (const edge of edges) {
    if (nodeIds.has(edge.source) && nodeIds.has(edge.target)) {
      const fromRank = COMMUNITY_NODE_RANK[nodeTypeMap.get(edge.source) ?? ''] ?? 2;
      const toRank = COMMUNITY_NODE_RANK[nodeTypeMap.get(edge.target) ?? ''] ?? 2;
      if (fromRank <= toRank) {
        g.setEdge(edge.source, edge.target);
      } else {
        g.setEdge(edge.target, edge.source);
      }
    }
  }

  dagre.layout(g);

  for (const node of nodes) {
    const n = g.node(node.id);
    if (n) {
      positions.set(node.id, { x: n.x - 100, y: n.y - 40 });
    }
  }

  return positions;
}

// ---- Filter bar types ----
interface NodeTypeToggle {
  key: CommunityNodeType;
  label: string;
  icon: React.ReactNode;
  activeColor: string;
}

const NODE_TYPE_TOGGLES: NodeTypeToggle[] = [
  { key: 'lead', label: 'Leads', icon: <Lightbulb className="h-3.5 w-3.5" />, activeColor: 'bg-blue-100 text-blue-800' },
  { key: 'person', label: 'Personen', icon: <User className="h-3.5 w-3.5" />, activeColor: 'bg-pink-100 text-pink-800' },
  { key: 'organisation', label: 'Organisaties', icon: <Building2 className="h-3.5 w-3.5" />, activeColor: 'bg-teal-100 text-teal-800' },
  { key: 'corpus_node', label: 'Beleidsnodes', icon: <FileText className="h-3.5 w-3.5" />, activeColor: 'bg-gray-100 text-gray-700' },
];

// ---- Inner component ----
interface CommunityGraphInnerProps {
  searchQuery?: string;
  initiatiefId: string;
  stageFilter?: string;
}

function CommunityGraphInner({
  searchQuery: searchQueryProp = '',
  initiatiefId,
  stageFilter: stageFilterProp = '',
}: CommunityGraphInnerProps) {
  const isMobile = useIsMobile();
  const { data, isLoading, error } = useCommunityGraph();
  const { openLeadDetail } = useLeadDetail();
  const { openNodeDetail } = useNodeDetail();

  // Stable refs so layout memo doesn't recompute on every render
  const openLeadDetailRef = useRef(openLeadDetail);
  openLeadDetailRef.current = openLeadDetail;
  const openNodeDetailRef = useRef(openNodeDetail);
  openNodeDetailRef.current = openNodeDetail;

  // Edge creation state (drag-to-connect)
  const [pendingConnection, setPendingConnection] = useState<Connection | null>(null);
  const handleConnect = useCallback((connection: Connection) => {
    if (connection.source && connection.target) {
      setPendingConnection(connection);
    }
  }, []);

  // Add contact state (+ button on lead nodes)
  const [addContactLeadId, setAddContactLeadId] = useState<string | null>(null);
  const addContactRef = useRef((leadId: string) => setAddContactLeadId(leadId));
  addContactRef.current = (leadId: string) => setAddContactLeadId(leadId);

  // View-specific filter: node type toggles
  const [enabledTypes, setEnabledTypes] = useState<Set<CommunityNodeType>>(
    new Set(['lead', 'person', 'organisation', 'corpus_node']),
  );

  const toggleType = useCallback((type: CommunityNodeType) => {
    setEnabledTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  }, []);

  // Build all RF nodes and edges from data (stable layout)
  const { allRfNodes, allRfEdges } = useMemo(() => {
    if (!data?.nodes?.length) return { allRfNodes: [], allRfEdges: [] };

    const positions = computeLayout(data.nodes, data.edges);

    const allRfNodes: RFNode<CommunityGraphNodeData>[] = data.nodes.map((node) => {
      const pos = positions.get(node.id) ?? { x: 0, y: 0 };
      // Determine click handler based on node type
      const rawId = node.id.replace(/^(lead|person|org|node)-/, '');
      let onClick: (() => void) | undefined;
      let onAddContact: (() => void) | undefined;
      if (node.node_type === 'lead') {
        onClick = () => openLeadDetailRef.current(rawId);
        onAddContact = () => addContactRef.current(rawId);
      } else if (node.node_type === 'corpus_node') {
        onClick = () => openNodeDetailRef.current(rawId);
      }

      return {
        id: node.id,
        type: 'communityNode',
        position: pos,
        data: {
          label: node.label,
          nodeType: node.node_type,
          stage: node.stage,
          initiatiefId: node.initiatief_id,
          functie: node.functie,
          orgType: node.org_type,
          corpusNodeType: node.corpus_node_type,
          onClick,
          onAddContact,
        },
      };
    });

    const allRfEdges: RFEdge[] = data.edges.map((edge) => {
      const style = edgeStyle(edge.edge_type);
      const fromPos = positions.get(edge.source);
      const toPos = positions.get(edge.target);
      const goesUpward = fromPos && toPos && fromPos.y > toPos.y;
      const marker = { type: MarkerType.ArrowClosed, width: 14, height: 14, color: style.color };

      return {
        id: edge.id,
        source: goesUpward ? edge.target : edge.source,
        target: goesUpward ? edge.source : edge.target,
        label: edge.label ?? style.label,
        type: 'bezier',
        animated: style.animated ?? false,
        ...(goesUpward ? { markerStart: marker } : { markerEnd: marker }),
        style: {
          stroke: style.color,
          strokeWidth: style.strokeWidth,
          strokeDasharray: style.strokeDasharray,
        },
        labelStyle: { fontSize: 10, fill: '#64748b', fontWeight: 500 },
        labelBgStyle: { fill: '#ffffff', fillOpacity: 0.9 },
        labelBgPadding: [4, 2] as [number, number],
        labelBgBorderRadius: 4,
      };
    });

    return { allRfNodes, allRfEdges };
  }, [data]);

  // Apply filters (type toggles, stage, initiative, search from props)
  const { rfNodes, rfEdges } = useMemo(() => {
    const q = searchQueryProp.toLowerCase();
    const visibleIds = new Set<string>();

    const rfNodes = allRfNodes.map((node) => {
      const d = node.data as CommunityGraphNodeData;
      const matchesType = enabledTypes.has(d.nodeType);
      const matchesStage = !stageFilterProp || d.nodeType !== 'lead' || d.stage === stageFilterProp;
      const matchesInitiatief = !initiatiefId || d.nodeType !== 'lead' || d.initiatiefId === initiatiefId;
      const matchesSearch = !q || d.label.toLowerCase().includes(q);
      const isVisible = matchesType && matchesStage && matchesInitiatief && matchesSearch;
      if (isVisible) visibleIds.add(node.id);
      return { ...node, hidden: !isVisible };
    });

    const rfEdges = allRfEdges.map((edge) => {
      const bothVisible = visibleIds.has(edge.source) && visibleIds.has(edge.target);
      return { ...edge, hidden: !bothVisible };
    });

    return { rfNodes, rfEdges };
  }, [allRfNodes, allRfEdges, enabledTypes, stageFilterProp, initiatiefId, searchQueryProp]);

  // React Flow state
  const [nodes, setNodes, onNodesChange] = useNodesState(rfNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(rfEdges);

  useEffect(() => {
    setNodes(rfNodes);
    setEdges(rfEdges);
  }, [rfNodes, rfEdges, setNodes, setEdges]);

  // Minimap coloring
  const minimapNodeColor = useCallback((node: RFNode) => {
    const d = node.data as CommunityGraphNodeData;
    return getNodeColor(d);
  }, []);

  if (isLoading) {
    return <LoadingSpinner className="py-8" />;
  }

  if (error) {
    return (
      <EmptyState
        title="Fout bij laden"
        description="Er is een fout opgetreden bij het laden van het netwerk. Probeer het opnieuw."
      />
    );
  }

  if (!data?.nodes?.length) {
    return (
      <EmptyState
        title="Geen data gevonden"
        description="Er zijn nog geen leads of gerelateerde gegevens om weer te geven in het netwerk."
      />
    );
  }

  return (
    <div className="space-y-4">
      <LeadMetricsBar />

      {/* Node type toggles */}
      <div className="flex items-center gap-2 flex-wrap">
        {NODE_TYPE_TOGGLES.map((toggle) => {
          const active = enabledTypes.has(toggle.key);
          return (
            <button
              key={toggle.key}
              onClick={() => toggleType(toggle.key)}
              className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                active ? toggle.activeColor : 'bg-gray-50 text-gray-400'
              }`}
            >
              {toggle.icon}
              {toggle.label}
            </button>
          );
        })}
      </div>

      {/* Graph canvas */}
      <div
        className="bg-white rounded-xl border border-border shadow-sm overflow-hidden"
        style={{ height: 'calc(100vh - 320px)', minHeight: isMobile ? '300px' : '500px' }}
      >
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
          defaultEdgeOptions={{ type: 'bezier' }}
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

      <CommunityEdgeModal
        pendingConnection={pendingConnection}
        onClose={() => setPendingConnection(null)}
      />

      <AddLeadContactModal
        leadId={addContactLeadId}
        onClose={() => setAddContactLeadId(null)}
      />
    </div>
  );
}

// Wrap in ReactFlowProvider
interface LeadGraphViewProps {
  searchQuery?: string;
  initiatiefId: string;
  stageFilter?: string;
}

export function LeadGraphView({ searchQuery, initiatiefId, stageFilter }: LeadGraphViewProps) {
  return (
    <ReactFlowProvider>
      <CommunityGraphInner
        searchQuery={searchQuery}
        initiatiefId={initiatiefId}
        stageFilter={stageFilter}
      />
    </ReactFlowProvider>
  );
}
