import { useVocabulary } from '@/contexts/VocabularyContext';
import { NodeType } from '@/types';
import type { SelectOption } from '@/components/common/CreatableSelect';

export function useNodeTypeOptions(): SelectOption[] {
  const { nodeLabel } = useVocabulary();
  return Object.values(NodeType).map((type) => ({
    value: type,
    label: nodeLabel(type),
  }));
}
