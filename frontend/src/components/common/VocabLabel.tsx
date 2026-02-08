import { useVocabulary } from '@/contexts/VocabularyContext';

interface VocabLabelProps {
  nodeType: string;
}

export function VocabLabel({ nodeType }: VocabLabelProps) {
  const { nodeLabel, nodeAltLabel } = useVocabulary();
  const label = nodeLabel(nodeType);
  const alt = nodeAltLabel(nodeType);

  return (
    <span title={label !== alt ? alt : undefined}>
      {label}
    </span>
  );
}
