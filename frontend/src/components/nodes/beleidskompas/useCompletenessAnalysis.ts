import { useMemo } from 'react';
import type { GraphViewResponse, CorpusNode } from '@/types';
import { BELEIDSKOMPAS_STEPS, type BeleidskompasStep } from './config';

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

    // Group subgraph nodes by type, excluding the dossier itself
    const nodesByType = new Map<string, CorpusNode[]>();
    for (const node of graphData.nodes) {
      if (node.id === dossierId) continue;
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
