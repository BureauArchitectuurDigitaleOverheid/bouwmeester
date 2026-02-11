import { useState, useCallback, useMemo } from 'react';
import { useNodes, useCreateNode } from '@/hooks/useNodes';
import { usePeople } from '@/hooks/usePeople';
import { useOrganisatieFlat } from '@/hooks/useOrganisatie';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { ORGANISATIE_TYPE_LABELS, NodeType, formatFunctie } from '@/types';
import type { SelectOption } from '@/components/common/CreatableSelect';

export function useTaskFormOptions() {
  const [personCreateName, setPersonCreateName] = useState('');
  const [showPersonCreate, setShowPersonCreate] = useState(false);

  const { nodeLabel } = useVocabulary();
  const createNode = useCreateNode();
  const { data: allNodes } = useNodes();
  const { data: allPeople } = usePeople();
  const { data: eenheden } = useOrganisatieFlat();

  const nodeOptions: SelectOption[] = useMemo(
    () => (allNodes ?? []).map((n) => ({
      value: n.id,
      label: n.title,
      description: nodeLabel(n.node_type),
    })),
    [allNodes, nodeLabel],
  );

  const personOptions: SelectOption[] = useMemo(
    () => (allPeople ?? []).map((p) => ({
      value: p.id,
      label: p.naam,
      description: formatFunctie(p.functie),
    })),
    [allPeople],
  );

  const eenheidOptions: SelectOption[] = useMemo(() => [
    { value: '', label: 'Geen' },
    ...(eenheden ?? []).map((e) => ({
      value: e.id,
      label: e.naam,
      description: ORGANISATIE_TYPE_LABELS[e.type] ?? e.type,
    })),
  ], [eenheden]);

  const handleCreateNode = useCallback(
    async (text: string): Promise<string | null> => {
      const node = await createNode.mutateAsync({
        title: text,
        node_type: NodeType.NOTITIE,
      });
      return node.id;
    },
    [createNode],
  );

  const handleCreatePerson = useCallback(
    async (text: string): Promise<string | null> => {
      setPersonCreateName(text);
      setShowPersonCreate(true);
      return null;
    },
    [],
  );

  return {
    nodeOptions,
    personOptions,
    eenheidOptions,
    handleCreateNode,
    handleCreatePerson,
    personCreateName,
    showPersonCreate,
    setShowPersonCreate,
  };
}
