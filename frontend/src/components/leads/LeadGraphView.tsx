import { useState, useMemo, useCallback, useEffect, useRef, memo, type CSSProperties } from 'react';
import {
  Building2,
  User,
  UserCircle2,
  FileText,
  Lightbulb,
  Plus,
  X,
  Handshake,
} from 'lucide-react';
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
  LEAD_STAGE_LABELS,
  LeadStage,
  NODE_TYPE_HEX_COLORS,
  NodeType,
  formatFunctie,
  SAMENWERKINGSVERBAND_TYPE_LABELS,
} from '@/types';
import type { CommunityGraphNode, CommunityGraphEdge } from '@/types';
import { stageTagColor } from './stageColors';

// ---- Hex colors per lead stage (for graph nodes) ----
const LEAD_STAGE_HEX: Record<string, string> = {
  verkennen: '#60A5FA',
  eerste_gesprek: '#FBBF24',
  interne_check: '#FB923C',
  follow_up: '#A78BFA',
  in_the_pocket: '#34D399',
  koelkast: '#9CA3AF',
};

/** `stageTagColor` gives an nldd-tag color name, which is also a valid
 * Rijkshuisstijl/semantic token segment (`--primitives-color-<name>-500` or
 * `--semantics-content-<name>-color` for the two semantic roles). This node
 * card renders its own chip with inline styles, matching the rest of
 * CommunityGraphNodeComponent's badges (all inline-styled — an nldd-tag
 * inside a reactflow-positioned node card would still need its host sized and
 * placed by hand, so there is no component win here), so the color has to
 * resolve to a CSS value rather than an nldd-tag `color` attribute. */
function stageTagColorVar(stage: string): string {
  const name = stageTagColor(stage);
  if (name === 'success' || name === 'warning' || name === 'critical' || name === 'accent') {
    return `var(--semantics-content-${name}-color)`;
  }
  return `var(--primitives-color-${name}-500)`;
}

const PERSON_INTERN_COLOR = '#EC4899';
const PERSON_EXTERN_COLOR = '#F97316';
const ORG_COLOR = '#14B8A6';
const SWV_COLOR = '#8B5CF6';
const CORPUS_NODE_FALLBACK = '#6B7280';

// ---- Community node type to rank (swim-lane y) ----
// Strikte horizontale swim-lanes per node-type, top-down. Y wordt opgelegd
// via LANE_Y; dagre regelt alleen nog x-positie en cross-minimization.
// Externe orgs bovenaan, interne thuis-organisaties helemaal onderaan
// (onder de interne mensen die er werken).
const RANK_ORG_EXTERN = 0;
const RANK_CORPUS_NODE = 1;
const RANK_LEAD = 2;
const RANK_SAMENWERKINGSVERBAND = 3;
const RANK_PERSON_EXTERN = 4;
const RANK_PERSON_INTERN = 5;
const RANK_ORG_INTERN = 6;
const RANK_DEFAULT = RANK_LEAD;

const LANE_Y: Record<number, number> = {
  [RANK_ORG_EXTERN]: 40,
  [RANK_CORPUS_NODE]: 240,
  [RANK_LEAD]: 440,
  [RANK_SAMENWERKINGSVERBAND]: 640,
  [RANK_PERSON_EXTERN]: 840,
  [RANK_PERSON_INTERN]: 1040,
  [RANK_ORG_INTERN]: 1240,
};

function getNodeRank(node: CommunityGraphNode): number {
  if (node.node_type === 'person') {
    return node.person_role === 'extern' ? RANK_PERSON_EXTERN : RANK_PERSON_INTERN;
  }
  if (node.node_type === 'organisation') {
    return node.org_role === 'intern' ? RANK_ORG_INTERN : RANK_ORG_EXTERN;
  }
  if (node.node_type === 'samenwerkingsverband') return RANK_SAMENWERKINGSVERBAND;
  if (node.node_type === 'corpus_node') return RANK_CORPUS_NODE;
  if (node.node_type === 'lead') return RANK_LEAD;
  return RANK_DEFAULT;
}

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
    case 'lid_van_swv':
      return {
        color: SWV_COLOR,
        strokeDasharray: '4 3',
        strokeWidth: 1.25,
        label: edgeType === 'lid_van_swv' ? 'lid' : edgeType,
      };
    default:
      // Corpus node edges and anything else
      return { color: '#94a3b8', strokeWidth: 1.5, label: edgeType.replace(/_/g, ' ') };
  }
}

// ---- Custom node component ----
type CommunityNodeType =
  | 'lead'
  | 'person'
  | 'organisation'
  | 'corpus_node'
  | 'samenwerkingsverband';

interface CommunityGraphNodeData {
  label: string;
  nodeType: CommunityNodeType;
  stage?: string | null;
  functie?: string | null;
  expertise?: string | null;
  personRole?: 'intern' | 'extern' | null;
  orgType?: string | null;
  orgRole?: 'intern' | 'extern' | null;
  swvType?: string | null;
  corpusNodeType?: string | null;
  dimmed?: boolean;
  onClick?: () => void;
  onAddContact?: () => void;
}

function getNodeColor(data: CommunityGraphNodeData): string {
  if (data.nodeType === 'lead') {
    return LEAD_STAGE_HEX[data.stage ?? ''] ?? '#9CA3AF';
  }
  if (data.nodeType === 'person') {
    return data.personRole === 'extern' ? PERSON_EXTERN_COLOR : PERSON_INTERN_COLOR;
  }
  if (data.nodeType === 'organisation') return ORG_COLOR;
  if (data.nodeType === 'samenwerkingsverband') return SWV_COLOR;
  if (data.nodeType === 'corpus_node' && data.corpusNodeType) {
    return NODE_TYPE_HEX_COLORS[data.corpusNodeType as NodeType] ?? CORPUS_NODE_FALLBACK;
  }
  return CORPUS_NODE_FALLBACK;
}

function CommunityGraphNodeComponent({ data }: NodeProps<CommunityGraphNodeData>) {
  const color = getNodeColor(data);
  const borderColor =
    data.nodeType === 'organisation' && data.orgRole === 'intern'
      ? PERSON_INTERN_COLOR
      : color;

  const badgeContent = (() => {
    if (data.nodeType === 'lead' && data.stage) {
      // De stage is sinds per-initiatief-kolommen een vrije slug. We pakken
      // alleen de vaste fallback-stijlen voor de 7 defaults; voor custom
      // kolommen valt de styling terug op een neutraal grijs en wordt de
      // slug zelf getoond — een per-graph-node lookup van de actieve
      // LeadColumn lijst zou hier overkill zijn.
      const fallbackKey = data.stage as LeadStage;
      const stageColor = stageTagColorVar(fallbackKey);
      return (
        <span
          style={{
            display: 'inline-block',
            borderRadius: '9999px',
            padding: '2px 8px',
            fontSize: '10px',
            fontWeight: 500,
            marginBottom: '4px',
            color: stageColor,
            // A light tint of the stage color as the chip background, same
            // idea as the person/org badges below (a hex color + low opacity).
            backgroundColor: `color-mix(in srgb, ${stageColor} 16%, transparent)`,
          }}
        >
          {LEAD_STAGE_LABELS[fallbackKey] ?? data.stage}
        </span>
      );
    }
    if (data.nodeType === 'person') {
      const isExtern = data.personRole === 'extern';
      const PersonIcon = isExtern ? UserCircle2 : User;
      const roleLabel = isExtern ? 'Extern' : 'Intern';
      const functieLabel = formatFunctie(data.functie);
      const label = functieLabel ? `${roleLabel} · ${functieLabel}` : roleLabel;
      return (
        <div style={{ marginBottom: '4px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <PersonIcon style={{ height: '12px', width: '12px', color }} />
            <span style={{ color, fontSize: '10px', fontWeight: 600, letterSpacing: '0.025em', textTransform: 'uppercase' }}>
              {label}
            </span>
          </div>
          {data.expertise && (
            <div style={{ color, fontSize: '9px', fontWeight: 500, marginTop: '1px', opacity: 0.85 }}>
              {data.expertise}
            </div>
          )}
        </div>
      );
    }
    if (data.nodeType === 'organisation') {
      const isIntern = data.orgRole === 'intern';
      const badgeColor = isIntern ? PERSON_INTERN_COLOR : color;
      const orgTypeLabel = data.orgType ?? 'Organisatie';
      const label = isIntern
        ? data.orgType
          ? `Intern · ${data.orgType}`
          : 'Intern'
        : orgTypeLabel;
      return (
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginBottom: '4px', minWidth: 0 }}>
          <Building2 style={{ height: '12px', width: '12px', flexShrink: 0, color: badgeColor }} />
          <span
            style={{
              color: badgeColor,
              fontSize: '10px',
              fontWeight: 600,
              letterSpacing: '0.025em',
              textTransform: 'uppercase',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {label}
          </span>
        </div>
      );
    }
    if (data.nodeType === 'corpus_node') {
      return (
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginBottom: '4px' }}>
          <FileText style={{ height: '12px', width: '12px', color }} />
          <span style={{ color, fontSize: '10px', fontWeight: 600, letterSpacing: '0.025em', textTransform: 'uppercase' }}>
            {data.corpusNodeType?.replace(/_/g, ' ') ?? 'Node'}
          </span>
        </div>
      );
    }
    if (data.nodeType === 'samenwerkingsverband') {
      const typeLabel = data.swvType
        ? SAMENWERKINGSVERBAND_TYPE_LABELS[data.swvType] ?? data.swvType
        : 'Verband';
      return (
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginBottom: '4px' }}>
          <Handshake style={{ height: '12px', width: '12px', color }} />
          <span style={{ color, fontSize: '10px', fontWeight: 600, letterSpacing: '0.025em', textTransform: 'uppercase' }}>
            {typeLabel}
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
        border: `1px solid ${borderColor}55`,
        minWidth: '160px',
        maxWidth: '220px',
        cursor: data.onClick ? 'pointer' : 'default',
        overflow: 'hidden',
        position: 'relative',
        opacity: data.dimmed ? 0.18 : 1,
        transition: 'opacity 150ms ease',
        pointerEvents: data.dimmed ? 'none' : 'auto',
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
  const nodeRankMap = new Map(nodes.map((n) => [n.id, getNodeRank(n)]));

  const nodeIds = new Set(nodes.map((n) => n.id));

  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  // We overschrijven dagre's y-output met LANE_Y, dus ranksep en edgesep
  // hebben geen visuele werking meer. nodesep en align bepalen nog wel
  // x-positie binnen een lane.
  g.setGraph({
    rankdir: 'TB',
    nodesep: 70,
    marginx: 40,
    marginy: 40,
    align: 'UL',
  });

  for (const node of nodes) {
    g.setNode(node.id, { width: 200, height: 80 });
  }

  for (const edge of edges) {
    if (nodeIds.has(edge.source) && nodeIds.has(edge.target)) {
      g.setEdge(edge.source, edge.target);
    }
  }

  dagre.layout(g);

  for (const node of nodes) {
    const n = g.node(node.id);
    if (n) {
      const rank = nodeRankMap.get(node.id) ?? RANK_DEFAULT;
      positions.set(node.id, { x: n.x - 100, y: LANE_Y[rank] ?? LANE_Y[RANK_DEFAULT] });
    }
  }

  return positions;
}

// ---- Filter bar types ----
interface NodeTypeToggle {
  key: CommunityNodeType;
  label: string;
  icon: React.ReactNode;
  /** A Rijkshuisstijl color-scale name; the chip reads its 500 step as
   *  foreground and a tint of it as background (see `.node-type-toggle`). */
  activeColorScale: string;
}

const ICON_SIZE_SM: CSSProperties = { height: '14px', width: '14px' };

const NODE_TYPE_TOGGLES: NodeTypeToggle[] = [
  { key: 'lead', label: 'Leads', icon: <Lightbulb style={ICON_SIZE_SM} />, activeColorScale: 'hemelblauw' },
  { key: 'person', label: 'Personen', icon: <User style={ICON_SIZE_SM} />, activeColorScale: 'roze' },
  { key: 'organisation', label: 'Organisaties', icon: <Building2 style={ICON_SIZE_SM} />, activeColorScale: 'groen' },
  { key: 'samenwerkingsverband', label: 'Verbanden', icon: <Handshake style={ICON_SIZE_SM} />, activeColorScale: 'paars' },
  { key: 'corpus_node', label: 'Beleidsnodes', icon: <FileText style={ICON_SIZE_SM} />, activeColorScale: 'neutral' },
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
  const { data, isLoading, error } = useCommunityGraph(initiatiefId || undefined);
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

  // Focus mode: dim everything outside a 2-hop neighbourhood around one node.
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);
  const setFocusRef = useRef((id: string | null) => setFocusedNodeId(id));
  setFocusRef.current = (id: string | null) => setFocusedNodeId(id);

  // View-specific filter: node type toggles
  const [enabledTypes, setEnabledTypes] = useState<Set<CommunityNodeType>>(
    new Set(['lead', 'person', 'organisation', 'samenwerkingsverband', 'corpus_node']),
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
      } else if (node.node_type === 'person' || node.node_type === 'organisation') {
        // Click on a person/organisation focuses the graph on that node's neighbourhood
        // instead of opening a detail panel (there is no detail panel for these).
        onClick = () => setFocusRef.current(node.id);
      }

      return {
        id: node.id,
        type: 'communityNode',
        position: pos,
        data: {
          label: node.label,
          nodeType: node.node_type,
          stage: node.stage,
          functie: node.functie,
          expertise: node.expertise,
          personRole: node.person_role ?? null,
          orgType: node.org_type,
          orgRole: node.org_role ?? null,
          swvType: node.samenwerkingsverband_type ?? null,
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
      const marker = { type: MarkerType.ArrowClosed, width: 16, height: 16, color: style.color };

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

  // A search query that matches a person's name auto-focuses on that person.
  // For non-person matches the query falls back to the existing hide-by-name behaviour.
  const searchFocusId = useMemo(() => {
    const q = searchQueryProp.trim().toLowerCase();
    if (!q) return null;
    const matchingPerson = allRfNodes.find((n) => {
      const d = n.data as CommunityGraphNodeData;
      return d.nodeType === 'person' && d.label.toLowerCase().includes(q);
    });
    return matchingPerson?.id ?? null;
  }, [allRfNodes, searchQueryProp]);

  // Active focus is either an explicit click-set focus or, if none, a search-driven focus.
  const activeFocusId = focusedNodeId ?? searchFocusId;

  // BFS over the (undirected) edge graph up to depth=2 from the focused node.
  const focusedSet = useMemo(() => {
    if (!activeFocusId) return null;
    const adjacency = new Map<string, Set<string>>();
    for (const edge of allRfEdges) {
      if (!adjacency.has(edge.source)) adjacency.set(edge.source, new Set());
      if (!adjacency.has(edge.target)) adjacency.set(edge.target, new Set());
      adjacency.get(edge.source)!.add(edge.target);
      adjacency.get(edge.target)!.add(edge.source);
    }
    const visited = new Set<string>([activeFocusId]);
    let frontier: string[] = [activeFocusId];
    for (let depth = 0; depth < 2; depth += 1) {
      const next: string[] = [];
      for (const id of frontier) {
        for (const nb of adjacency.get(id) ?? []) {
          if (!visited.has(nb)) {
            visited.add(nb);
            next.push(nb);
          }
        }
      }
      frontier = next;
      if (frontier.length === 0) break;
    }
    return visited;
  }, [activeFocusId, allRfEdges]);

  // Apply filters (type toggles, stage, initiative) and focus dimming.
  // Search-as-hide only kicks in when the query does not match a person — otherwise
  // the matching person becomes the focus target and everything stays visible-but-dimmed.
  const { rfNodes, rfEdges } = useMemo(() => {
    const q = searchQueryProp.trim().toLowerCase();
    const searchActsAsFocus = searchFocusId !== null;
    const visibleIds = new Set<string>();

    const rfNodes = allRfNodes.map((node) => {
      const d = node.data as CommunityGraphNodeData;
      const matchesType = enabledTypes.has(d.nodeType);
      const matchesStage = !stageFilterProp || d.nodeType !== 'lead' || d.stage === stageFilterProp;
      const matchesSearch = !q || searchActsAsFocus || d.label.toLowerCase().includes(q);
      const isVisible = matchesType && matchesStage && matchesSearch;
      if (isVisible) visibleIds.add(node.id);
      const dimmed = isVisible && focusedSet !== null && !focusedSet.has(node.id);
      return { ...node, hidden: !isVisible, data: { ...d, dimmed } };
    });

    const rfEdges = allRfEdges.map((edge) => {
      const bothVisible = visibleIds.has(edge.source) && visibleIds.has(edge.target);
      const dimmed =
        bothVisible &&
        focusedSet !== null &&
        !(focusedSet.has(edge.source) && focusedSet.has(edge.target));
      const baseStyle = edge.style ?? {};
      return {
        ...edge,
        hidden: !bothVisible,
        style: dimmed ? { ...baseStyle, opacity: 0.12 } : { ...baseStyle, opacity: 1 },
        labelStyle: dimmed
          ? { ...edge.labelStyle, opacity: 0.2 }
          : edge.labelStyle,
      };
    });

    return { rfNodes, rfEdges };
  }, [
    allRfNodes,
    allRfEdges,
    enabledTypes,
    stageFilterProp,
    searchQueryProp,
    searchFocusId,
    focusedSet,
  ]);

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
    return <LoadingSpinner padding="32" />;
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
    <nldd-container gap="16">
      <LeadMetricsBar initiatiefId={initiatiefId || undefined} />

      {/* Node type toggles + focus indicator */}
      <div className="node-type-toggle-row">
        {NODE_TYPE_TOGGLES.map((toggle) => {
          const active = enabledTypes.has(toggle.key);
          return (
            <button
              key={toggle.key}
              onClick={() => toggleType(toggle.key)}
              className="node-type-toggle"
              style={active ? {
                color: `var(--primitives-color-${toggle.activeColorScale}-800)`,
                backgroundColor: `var(--primitives-color-${toggle.activeColorScale}-100)`,
              } : undefined}
            >
              {toggle.icon}
              {toggle.label}
            </button>
          );
        })}
        {focusedNodeId && (
          <button
            onClick={() => setFocusedNodeId(null)}
            className="node-type-toggle node-type-toggle-focus"
            title="Toon weer alle nodes"
          >
            <X style={ICON_SIZE_SM} />
            Focus opheffen
          </button>
        )}
      </div>

      {/* Graph canvas */}
      <div
        className="graph-canvas-frame"
        style={{ height: 'calc(100vh - 320px)', minHeight: isMobile ? '300px' : '500px' }}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={handleConnect}
          onPaneClick={() => setFocusedNodeId(null)}
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
    </nldd-container>
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
