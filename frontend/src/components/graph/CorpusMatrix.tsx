import { useMemo } from 'react';
import { Card } from '@/components/common/Card';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { useGraphView } from '@/hooks/useGraph';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { NODE_TYPE_HEX_COLORS } from '@/types';
import type { NodeType, CorpusNode, Edge } from '@/types';

interface CorpusMatrixProps {
  rowNodeType: NodeType;
  colNodeType: NodeType;
  enabledEdgeTypes: Set<string>;
  searchQuery?: string;
}

interface CellEdge {
  id: string;
  edge_type_id: string;
}

export function CorpusMatrix({
  rowNodeType,
  colNodeType,
  enabledEdgeTypes,
  searchQuery,
}: CorpusMatrixProps) {
  const { data: graphData, isLoading } = useGraphView(undefined, undefined, true);
  const { edgeLabel } = useVocabulary();
  const { openNodeDetail } = useNodeDetail();

  // Filter nodes by type, then optionally by search
  const rowNodes = useMemo(() => {
    if (!graphData?.nodes) return [];
    let nodes = graphData.nodes.filter((n: CorpusNode) => n.node_type === rowNodeType);
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      nodes = nodes.filter((n: CorpusNode) => n.title.toLowerCase().includes(q));
    }
    return nodes.sort((a: CorpusNode, b: CorpusNode) => a.title.localeCompare(b.title));
  }, [graphData?.nodes, rowNodeType, searchQuery]);

  const colNodes = useMemo(() => {
    if (!graphData?.nodes) return [];
    let nodes = graphData.nodes.filter((n: CorpusNode) => n.node_type === colNodeType);
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      nodes = nodes.filter((n: CorpusNode) => n.title.toLowerCase().includes(q));
    }
    return nodes.sort((a: CorpusNode, b: CorpusNode) => a.title.localeCompare(b.title));
  }, [graphData?.nodes, colNodeType, searchQuery]);

  // Build adjacency lookup: key = `${rowNodeId}_${colNodeId}` -> edges[]
  const adjacency = useMemo(() => {
    if (!graphData?.edges) return new Map<string, CellEdge[]>();

    const rowIds = new Set(rowNodes.map((n: CorpusNode) => n.id));
    const colIds = new Set(colNodes.map((n: CorpusNode) => n.id));
    const map = new Map<string, CellEdge[]>();

    for (const edge of graphData.edges) {
      if (!enabledEdgeTypes.has(edge.edge_type_id)) continue;

      // Check both directions
      let rowId: string | null = null;
      let colId: string | null = null;

      if (rowIds.has(edge.from_node_id) && colIds.has(edge.to_node_id)) {
        rowId = edge.from_node_id;
        colId = edge.to_node_id;
      } else if (rowIds.has(edge.to_node_id) && colIds.has(edge.from_node_id)) {
        rowId = edge.to_node_id;
        colId = edge.from_node_id;
      }

      if (rowId && colId) {
        const key = `${rowId}_${colId}`;
        const existing = map.get(key) ?? [];
        existing.push({ id: edge.id, edge_type_id: edge.edge_type_id });
        map.set(key, existing);
      }
    }

    return map;
  }, [graphData?.edges, rowNodes, colNodes, enabledEdgeTypes]);

  if (isLoading) {
    return <LoadingSpinner className="py-12" />;
  }

  if (rowNodes.length === 0 && colNodes.length === 0) {
    return <EmptyState message="Geen nodes gevonden voor de geselecteerde types." />;
  }

  if (rowNodes.length === 0) {
    return <EmptyState message="Geen rij-nodes gevonden voor het geselecteerde type." />;
  }

  if (colNodes.length === 0) {
    return <EmptyState message="Geen kolom-nodes gevonden voor het geselecteerde type." />;
  }

  const rowColor = NODE_TYPE_HEX_COLORS[rowNodeType];
  const colColor = NODE_TYPE_HEX_COLORS[colNodeType];

  // Count total connections
  const connectionCount = Array.from(adjacency.values()).reduce(
    (sum, edges) => sum + edges.length,
    0,
  );

  return (
    <div className="space-y-3">
      <p className="text-xs text-text-secondary">
        {rowNodes.length} rijen &times; {colNodes.length} kolommen &middot;{' '}
        {connectionCount} {connectionCount === 1 ? 'relatie' : 'relaties'}
      </p>

      <Card padding={false}>
        <div className="overflow-auto max-h-[calc(100vh-280px)]">
          <table className="text-xs border-collapse">
            <thead className="sticky top-0 z-20">
              <tr>
                {/* Top-left corner cell */}
                <th className="sticky left-0 z-30 bg-gray-50 border-b border-r border-border min-w-[180px] max-w-[220px] px-3 py-2" />
                {/* Column headers */}
                {colNodes.map((col: CorpusNode) => (
                  <th
                    key={col.id}
                    className="bg-gray-50 border-b border-border px-1 py-2 font-medium text-center min-w-[40px]"
                  >
                    <button
                      onClick={() => openNodeDetail(col.id)}
                      className="block w-full hover:text-primary-600 transition-colors"
                      title={col.title}
                    >
                      <span
                        className="writing-mode-vertical inline-block max-h-[140px] overflow-hidden text-ellipsis whitespace-nowrap"
                        style={{
                          writingMode: 'vertical-rl',
                          transform: 'rotate(180deg)',
                          color: colColor,
                        }}
                      >
                        {col.title}
                      </span>
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rowNodes.map((row: CorpusNode) => (
                <tr key={row.id} className="hover:bg-gray-50/50">
                  {/* Row header */}
                  <td className="sticky left-0 z-10 bg-white border-r border-border px-3 py-1.5 min-w-[180px] max-w-[220px]">
                    <button
                      onClick={() => openNodeDetail(row.id)}
                      className="text-left truncate block w-full hover:text-primary-600 font-medium transition-colors"
                      title={row.title}
                      style={{ color: rowColor }}
                    >
                      {row.title}
                    </button>
                  </td>
                  {/* Data cells */}
                  {colNodes.map((col: CorpusNode) => {
                    const key = `${row.id}_${col.id}`;
                    const cellEdges = adjacency.get(key);
                    const hasEdge = cellEdges && cellEdges.length > 0;

                    return (
                      <td
                        key={col.id}
                        className="border-b border-border/50 px-1 py-1.5 text-center"
                      >
                        {hasEdge ? (
                          <button
                            onClick={() => openNodeDetail(row.id)}
                            className="inline-flex items-center justify-center h-6 w-6 rounded-full transition-colors hover:ring-2 hover:ring-primary-300"
                            title={cellEdges
                              .map((e: CellEdge) => edgeLabel(e.edge_type_id))
                              .join(', ')}
                          >
                            <span
                              className="block h-3 w-3 rounded-full"
                              style={{
                                backgroundColor:
                                  cellEdges.length === 1
                                    ? NODE_TYPE_HEX_COLORS[rowNodeType]
                                    : '#6366F1',
                                opacity: 0.8,
                              }}
                            />
                          </button>
                        ) : (
                          <span className="inline-block h-6 w-6" />
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
