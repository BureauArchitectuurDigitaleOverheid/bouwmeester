import { useVocabulary } from '@/contexts/VocabularyContext';
import { NodeType } from '@/types';
import type { SelectOption } from '@/components/common/CreatableSelect';

/** Node types that should not be manually created (they come from imports). */
const EXCLUDED_FROM_CREATE = new Set<NodeType>([NodeType.POLITIEKE_INPUT]);

export function useNodeTypeOptions(): SelectOption[] {
  const { nodeLabel } = useVocabulary();
  return Object.values(NodeType)
    .filter((type) => !EXCLUDED_FROM_CREATE.has(type))
    .map((type) => ({
      value: type,
      label: nodeLabel(type),
    }));
}
