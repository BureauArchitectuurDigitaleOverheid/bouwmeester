export interface CellEdge {
  id: string;
  edge_type_id: string;
}

interface EdgeInput {
  id: string;
  from_node_id: string;
  to_node_id: string;
  edge_type_id: string;
}

/**
 * Build an adjacency map for the matrix view.
 *
 * Keys are `${rowNodeId}_${colNodeId}`, values are the edges connecting them.
 * Edges are direction-agnostic: an edge A→B shows up in both (A,B) and (B,A)
 * when row/col types are the same (symmetric matrix).
 *
 * When `sameType` is true, each edge is placed in both mirror cells but only
 * counted once (deduplication via edge id). Self-edges on the diagonal are skipped.
 */
export function buildMatrixAdjacency(
  edges: EdgeInput[],
  rowIds: Set<string>,
  colIds: Set<string>,
  enabledEdgeTypes: Set<string>,
  sameType: boolean,
): Map<string, CellEdge[]> {
  const map = new Map<string, CellEdge[]>();

  for (const edge of edges) {
    if (!enabledEdgeTypes.has(edge.edge_type_id)) continue;

    // Determine which endpoint is a row node and which is a column node
    let rowId: string | null = null;
    let colId: string | null = null;

    if (rowIds.has(edge.from_node_id) && colIds.has(edge.to_node_id)) {
      rowId = edge.from_node_id;
      colId = edge.to_node_id;
    } else if (rowIds.has(edge.to_node_id) && colIds.has(edge.from_node_id)) {
      rowId = edge.to_node_id;
      colId = edge.from_node_id;
    }

    if (!rowId || !colId) continue;

    const cellEdge: CellEdge = { id: edge.id, edge_type_id: edge.edge_type_id };

    if (sameType) {
      // Skip self-edges (diagonal)
      if (rowId === colId) continue;

      // Place in both (row,col) and (col,row) for symmetric display
      for (const [r, c] of [[rowId, colId], [colId, rowId]] as [string, string][]) {
        const key = `${r}_${c}`;
        const existing = map.get(key) ?? [];
        // Avoid duplicate edge entries in the same cell (an edge only matches once per cell)
        if (!existing.some((e) => e.id === edge.id)) {
          existing.push(cellEdge);
          map.set(key, existing);
        }
      }
    } else {
      const key = `${rowId}_${colId}`;
      const existing = map.get(key) ?? [];
      existing.push(cellEdge);
      map.set(key, existing);
    }
  }

  return map;
}

/**
 * Count unique edges in the adjacency map (avoids double-counting mirrored cells).
 */
export function countUniqueEdges(adjacency: Map<string, CellEdge[]>): number {
  const edgeIds = new Set<string>();
  for (const edges of adjacency.values()) {
    for (const e of edges) edgeIds.add(e.id);
  }
  return edgeIds.size;
}
