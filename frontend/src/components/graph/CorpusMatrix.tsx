import { useMemo, useState } from 'react';
import { Card } from '@/components/common/Card';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { NODE_TYPE_HEX_COLORS } from '@/types';
import type { NodeType, CorpusNode, GraphViewResponse } from '@/types';
import { buildMatrixAdjacency, countUniqueEdges, type CellEdge } from '@/utils/matrixAdjacency';

const MAX_MATRIX_DIMENSION = 100;

interface CorpusMatrixProps {
  rowNodeType: NodeType;
  colNodeType: NodeType;
  enabledEdgeTypes: Set<string>;
  searchQuery?: string;
  graphData?: GraphViewResponse;
  isLoading: boolean;
}

export function CorpusMatrix({
  rowNodeType,
  colNodeType,
  enabledEdgeTypes,
  searchQuery,
  graphData,
  isLoading,
}: CorpusMatrixProps) {
  const { edgeLabel } = useVocabulary();
  const { openNodeDetail } = useNodeDetail();
  const [showFullMatrix, setShowFullMatrix] = useState(false);

  const sameType = rowNodeType === colNodeType;

  // Filter nodes by type, then optionally by search
  const allRowNodes = useMemo(() => {
    if (!graphData?.nodes) return [];
    let nodes = graphData.nodes.filter((n: CorpusNode) => n.node_type === rowNodeType);
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      nodes = nodes.filter((n: CorpusNode) => n.title.toLowerCase().includes(q));
    }
    return nodes.sort((a: CorpusNode, b: CorpusNode) => a.title.localeCompare(b.title));
  }, [graphData?.nodes, rowNodeType, searchQuery]);

  const allColNodes = useMemo(() => {
    if (!graphData?.nodes) return [];
    if (sameType) return allRowNodes;
    let nodes = graphData.nodes.filter((n: CorpusNode) => n.node_type === colNodeType);
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      nodes = nodes.filter((n: CorpusNode) => n.title.toLowerCase().includes(q));
    }
    return nodes.sort((a: CorpusNode, b: CorpusNode) => a.title.localeCompare(b.title));
  }, [graphData?.nodes, colNodeType, searchQuery, sameType, allRowNodes]);

  // Apply dimension cap unless user opted to show full matrix
  const isTruncated = !showFullMatrix && (allRowNodes.length > MAX_MATRIX_DIMENSION || allColNodes.length > MAX_MATRIX_DIMENSION);
  const rowNodes = isTruncated ? allRowNodes.slice(0, MAX_MATRIX_DIMENSION) : allRowNodes;
  const colNodes = isTruncated ? allColNodes.slice(0, MAX_MATRIX_DIMENSION) : allColNodes;

  // Build adjacency using the extracted utility
  const adjacency = useMemo(() => {
    if (!graphData?.edges) return new Map<string, CellEdge[]>();
    const rowIds = new Set(rowNodes.map((n: CorpusNode) => n.id));
    const colIds = new Set(colNodes.map((n: CorpusNode) => n.id));
    return buildMatrixAdjacency(graphData.edges, rowIds, colIds, enabledEdgeTypes, sameType);
  }, [graphData?.edges, rowNodes, colNodes, enabledEdgeTypes, sameType]);

  if (isLoading) {
    return <LoadingSpinner className="py-12" />;
  }

  if (allRowNodes.length === 0 && allColNodes.length === 0) {
    return <EmptyState message="Geen nodes gevonden voor de geselecteerde types." />;
  }

  if (allRowNodes.length === 0) {
    return <EmptyState message="Geen rij-nodes gevonden voor het geselecteerde type." />;
  }

  if (allColNodes.length === 0) {
    return <EmptyState message="Geen kolom-nodes gevonden voor het geselecteerde type." />;
  }

  const rowColor = NODE_TYPE_HEX_COLORS[rowNodeType];
  const colColor = NODE_TYPE_HEX_COLORS[colNodeType];
  const connectionCount = countUniqueEdges(adjacency);

  return (
    <div className="space-y-3">
      <p className="text-xs text-text-secondary">
        {rowNodes.length}{isTruncated && allRowNodes.length > MAX_MATRIX_DIMENSION ? ` van ${allRowNodes.length}` : ''} rijen
        {' '}&times;{' '}
        {colNodes.length}{isTruncated && allColNodes.length > MAX_MATRIX_DIMENSION ? ` van ${allColNodes.length}` : ''} kolommen
        {' '}&middot;{' '}
        {connectionCount} {connectionCount === 1 ? 'relatie' : 'relaties'}
      </p>

      {isTruncated && (
        <div className="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          <span>
            Matrix is beperkt tot {MAX_MATRIX_DIMENSION}&times;{MAX_MATRIX_DIMENSION} voor prestatie.
            Gebruik de zoekbalk om te filteren, of{' '}
            <button
              onClick={() => setShowFullMatrix(true)}
              className="underline font-medium hover:text-amber-900"
            >
              toon alles ({allRowNodes.length}&times;{allColNodes.length})
            </button>.
          </span>
        </div>
      )}

      <Card padding={false}>
        <div className="overflow-auto max-h-[calc(100vh-280px)]">
          <table className="text-xs border-collapse">
            <thead className="sticky top-0 z-20">
              <tr>
                <th className="sticky left-0 z-30 bg-gray-50 border-b border-r border-border min-w-[180px] max-w-[220px] px-3 py-2" />
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
                <tr key={row.id} className="group">
                  {/* Row header — opaque bg prevents bleed-through on horizontal scroll */}
                  <td className="sticky left-0 z-10 bg-white group-hover:bg-gray-50 border-r border-border px-3 py-1.5 min-w-[180px] max-w-[220px]">
                    <button
                      onClick={() => openNodeDetail(row.id)}
                      className="text-left truncate block w-full hover:text-primary-600 font-medium transition-colors"
                      title={row.title}
                      style={{ color: rowColor }}
                    >
                      {row.title}
                    </button>
                  </td>
                  {colNodes.map((col: CorpusNode) => {
                    const key = `${row.id}_${col.id}`;
                    const cellEdges = adjacency.get(key);
                    const hasEdge = cellEdges && cellEdges.length > 0;
                    const isDiagonal = sameType && row.id === col.id;

                    // Build tooltip: edge types + both node titles
                    const tooltip = hasEdge
                      ? `${row.title} — ${cellEdges.map((e: CellEdge) => edgeLabel(e.edge_type_id)).join(', ')} — ${col.title}`
                      : undefined;

                    return (
                      <td
                        key={col.id}
                        className={`border-b border-border/50 px-1 py-1.5 text-center group-hover:bg-gray-50/50 ${isDiagonal ? 'bg-gray-100' : ''}`}
                      >
                        {isDiagonal ? (
                          <span className="inline-block h-6 w-6 text-gray-300">&mdash;</span>
                        ) : hasEdge ? (
                          <button
                            onClick={() => openNodeDetail(col.id)}
                            className="inline-flex items-center justify-center h-6 w-6 rounded-full transition-colors hover:ring-2 hover:ring-primary-300"
                            title={tooltip}
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
