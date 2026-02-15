import { useMemo } from 'react';
import type { GraphViewResponse, CorpusNode } from '@/types';
import { BELEIDSKOMPAS_STEPS, type BeleidskompasStep } from './config';
import { EDGE_TYPE_ONDERDEEL_VAN } from './constants';

export interface StepStatus {
  step: BeleidskompasStep;
  nodes: CorpusNode[];
  count: number;
  isComplete: boolean;
}

export function useCompletenessAnalysis(
  graphData: GraphViewResponse | undefined,
  dossierId: string,
): { steps: StepStatus[]; completedCount: number; totalSteps: number } {
  return useMemo(() => {
    if (!graphData) {
      return {
        steps: BELEIDSKOMPAS_STEPS.map((step) => ({
          step,
          nodes: [],
          count: 0,
          isComplete: false,
        })),
        completedCount: 0,
        totalSteps: BELEIDSKOMPAS_STEPS.length,
      };
    }

    // Build a set of node IDs directly linked to the dossier via onderdeel_van edges.
    // The edge direction is: child --onderdeel_van--> dossier (to_node_id = dossierId).
    const directChildIds = new Set<string>();
    for (const edge of graphData.edges) {
      if (
        edge.edge_type_id === EDGE_TYPE_ONDERDEEL_VAN &&
        edge.to_node_id === dossierId
      ) {
        directChildIds.add(edge.from_node_id);
      }
    }

    // Index nodes by id for fast lookup
    const nodesById = new Map<string, CorpusNode>();
    for (const node of graphData.nodes) {
      nodesById.set(node.id, node);
    }

    // Group only directly-linked nodes by type
    const nodesByType = new Map<string, CorpusNode[]>();
    for (const childId of directChildIds) {
      const node = nodesById.get(childId);
      if (!node) continue;
      const existing = nodesByType.get(node.node_type) ?? [];
      existing.push(node);
      nodesByType.set(node.node_type, existing);
    }

    const steps: StepStatus[] = BELEIDSKOMPAS_STEPS.map((step) => {
      const nodes = nodesByType.get(step.nodeType) ?? [];
      return {
        step,
        nodes,
        count: nodes.length,
        isComplete: nodes.length > 0,
      };
    });

    const completedCount = steps.filter((s) => s.isComplete).length;

    return { steps, completedCount, totalSteps: BELEIDSKOMPAS_STEPS.length };
  }, [graphData, dossierId]);
}
