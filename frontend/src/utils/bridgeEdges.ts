import type { CorpusNode, Edge } from '@/types';

export interface BridgeEdge {
  id: string;
  from_node_id: string;
  to_node_id: string;
  isBridge: true;
  bridgedThrough: string[];
}

/**
 * Generate bridge edges for filtered-out nodes.
 *
 * When a node is hidden by filters but connects two visible nodes, a dashed
 * "bridge" edge is created between those visible neighbours so the user can
 * still see that an indirect relationship exists.
 */
export function generateBridgeEdges(
  allNodes: CorpusNode[],
  allEdges: Edge[],
  visibleNodes: CorpusNode[],
): { visibleEdges: Edge[]; bridgeEdges: BridgeEdge[] } {
  const visibleNodeIds = new Set(visibleNodes.map((n) => n.id));
  const filteredOutNodeIds = allNodes
    .filter((n) => !visibleNodeIds.has(n.id))
    .map((n) => n.id);

  // Build adjacency map (undirected) from all edges
  const adjacencyMap = new Map<string, Set<string>>();
  for (const edge of allEdges) {
    if (!adjacencyMap.has(edge.from_node_id)) {
      adjacencyMap.set(edge.from_node_id, new Set());
    }
    if (!adjacencyMap.has(edge.to_node_id)) {
      adjacencyMap.set(edge.to_node_id, new Set());
    }
    adjacencyMap.get(edge.from_node_id)!.add(edge.to_node_id);
    adjacencyMap.get(edge.to_node_id)!.add(edge.from_node_id);
  }

  // Keep original edges where both endpoints are visible
  const visibleEdges = allEdges.filter(
    (e) => visibleNodeIds.has(e.from_node_id) && visibleNodeIds.has(e.to_node_id),
  );

  // Generate bridge edges
  const bridgeEdges: BridgeEdge[] = [];
  const bridgeSet = new Set<string>(); // avoid duplicates

  for (const filteredNodeId of filteredOutNodeIds) {
    const neighbors = adjacencyMap.get(filteredNodeId);
    if (!neighbors) continue;

    const visibleNeighbors = Array.from(neighbors).filter((id) => visibleNodeIds.has(id));

    // Create bridge edges between all pairs of visible neighbours
    for (let i = 0; i < visibleNeighbors.length; i++) {
      for (let j = i + 1; j < visibleNeighbors.length; j++) {
        const nodeA = visibleNeighbors[i];
        const nodeB = visibleNeighbors[j];

        // Sorted key to avoid A-B vs B-A duplicates
        const edgeKey = [nodeA, nodeB].sort().join('-');

        if (!bridgeSet.has(edgeKey)) {
          bridgeSet.add(edgeKey);

          const existingBridge = bridgeEdges.find(
            (b) =>
              (b.from_node_id === nodeA && b.to_node_id === nodeB) ||
              (b.from_node_id === nodeB && b.to_node_id === nodeA),
          );

          if (existingBridge) {
            existingBridge.bridgedThrough.push(filteredNodeId);
          } else {
            bridgeEdges.push({
              id: `bridge-${nodeA}-${nodeB}`,
              from_node_id: nodeA,
              to_node_id: nodeB,
              isBridge: true,
              bridgedThrough: [filteredNodeId],
            });
          }
        }
      }
    }
  }

  // Merge bridge paths that go through multiple filtered nodes
  const mergedBridges = mergeBridgePaths(bridgeEdges);

  return { visibleEdges, bridgeEdges: mergedBridges };
}

/**
 * Merge bridge edges that share the same pair of endpoints, combining their
 * bridgedThrough arrays.
 */
function mergeBridgePaths(bridgeEdges: BridgeEdge[]): BridgeEdge[] {
  const bridgeMap = new Map<string, BridgeEdge>();

  for (const bridge of bridgeEdges) {
    const key = [bridge.from_node_id, bridge.to_node_id].sort().join('-');
    const existing = bridgeMap.get(key);

    if (existing) {
      const mergedThrough = new Set([...existing.bridgedThrough, ...bridge.bridgedThrough]);
      existing.bridgedThrough = Array.from(mergedThrough);
    } else {
      bridgeMap.set(key, { ...bridge });
    }
  }

  return Array.from(bridgeMap.values());
}
