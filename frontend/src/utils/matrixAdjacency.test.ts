import { describe, it, expect } from 'vitest';
import { buildMatrixAdjacency, countUniqueEdges } from './matrixAdjacency';

function edge(id: string, from: string, to: string, type = 'related') {
  return { id, from_node_id: from, to_node_id: to, edge_type_id: type };
}

describe('buildMatrixAdjacency', () => {
  it('places an edge in the correct cell (from=row, to=col)', () => {
    const edges = [edge('e1', 'r1', 'c1')];
    const result = buildMatrixAdjacency(
      edges,
      new Set(['r1']),
      new Set(['c1']),
      new Set(['related']),
      false,
    );

    expect(result.get('r1_c1')).toEqual([{ id: 'e1', edge_type_id: 'related' }]);
    expect(result.has('c1_r1')).toBe(false);
  });

  it('places an edge when direction is reversed (from=col, to=row)', () => {
    const edges = [edge('e1', 'c1', 'r1')];
    const result = buildMatrixAdjacency(
      edges,
      new Set(['r1']),
      new Set(['c1']),
      new Set(['related']),
      false,
    );

    expect(result.get('r1_c1')).toEqual([{ id: 'e1', edge_type_id: 'related' }]);
  });

  it('filters out edges whose type is not enabled', () => {
    const edges = [
      edge('e1', 'r1', 'c1', 'related'),
      edge('e2', 'r1', 'c1', 'blocked'),
    ];
    const result = buildMatrixAdjacency(
      edges,
      new Set(['r1']),
      new Set(['c1']),
      new Set(['related']),
      false,
    );

    expect(result.get('r1_c1')).toHaveLength(1);
    expect(result.get('r1_c1')![0].id).toBe('e1');
  });

  it('ignores edges that do not connect row and column nodes', () => {
    const edges = [edge('e1', 'x1', 'x2')];
    const result = buildMatrixAdjacency(
      edges,
      new Set(['r1']),
      new Set(['c1']),
      new Set(['related']),
      false,
    );

    expect(result.size).toBe(0);
  });

  it('accumulates multiple edges in the same cell', () => {
    const edges = [
      edge('e1', 'r1', 'c1', 'related'),
      edge('e2', 'r1', 'c1', 'implements'),
    ];
    const result = buildMatrixAdjacency(
      edges,
      new Set(['r1']),
      new Set(['c1']),
      new Set(['related', 'implements']),
      false,
    );

    expect(result.get('r1_c1')).toHaveLength(2);
  });

  describe('sameType = true (symmetric matrix)', () => {
    it('mirrors edges into both (A,B) and (B,A) cells', () => {
      const edges = [edge('e1', 'n1', 'n2')];
      const nodeIds = new Set(['n1', 'n2']);
      const result = buildMatrixAdjacency(
        edges,
        nodeIds,
        nodeIds,
        new Set(['related']),
        true,
      );

      expect(result.get('n1_n2')).toEqual([{ id: 'e1', edge_type_id: 'related' }]);
      expect(result.get('n2_n1')).toEqual([{ id: 'e1', edge_type_id: 'related' }]);
    });

    it('skips self-edges (diagonal)', () => {
      const edges = [edge('e1', 'n1', 'n1')];
      const nodeIds = new Set(['n1']);
      const result = buildMatrixAdjacency(
        edges,
        nodeIds,
        nodeIds,
        new Set(['related']),
        true,
      );

      expect(result.size).toBe(0);
    });

    it('does not duplicate edge entries in a cell', () => {
      // Edge from n1→n2 should only appear once in the n1_n2 cell,
      // even though the bidirectional check might match twice
      const edges = [edge('e1', 'n1', 'n2')];
      const nodeIds = new Set(['n1', 'n2']);
      const result = buildMatrixAdjacency(
        edges,
        nodeIds,
        nodeIds,
        new Set(['related']),
        true,
      );

      expect(result.get('n1_n2')).toHaveLength(1);
      expect(result.get('n2_n1')).toHaveLength(1);
    });
  });
});

describe('countUniqueEdges', () => {
  it('counts unique edge ids across all cells', () => {
    const map = new Map([
      ['a_b', [{ id: 'e1', edge_type_id: 'x' }]],
      ['b_a', [{ id: 'e1', edge_type_id: 'x' }]], // same edge, mirrored
      ['a_c', [{ id: 'e2', edge_type_id: 'y' }]],
    ]);

    expect(countUniqueEdges(map)).toBe(2);
  });

  it('returns 0 for empty map', () => {
    expect(countUniqueEdges(new Map())).toBe(0);
  });
});
