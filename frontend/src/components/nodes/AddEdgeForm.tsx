import { useState, useCallback, useMemo } from 'react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { Button } from '@/components/common/Button';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { useCreateEdge } from '@/hooks/useEdges';
import { useNodes, useCreateNode } from '@/hooks/useNodes';
import { useValidEdgeTypes } from '@/hooks/useEdgeTypes';
import { NodeType } from '@/types';
import type { SelectOption } from '@/components/common/CreatableSelect';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { EDGE_TYPE_VOCABULARY } from '@/vocabulary';

interface AddEdgeFormProps {
  open: boolean;
  onClose: () => void;
  sourceNodeId: string;
  sourceNodeType?: string;
}

export function AddEdgeForm({ open, onClose, sourceNodeId, sourceNodeType }: AddEdgeFormProps) {
  const { nodeLabel, edgeLabel: vocabEdgeLabel } = useVocabulary();
  const [targetId, setTargetId] = useState('');
  const [edgeType, setEdgeType] = useState('');
  const [description, setDescription] = useState('');
  const createEdge = useCreateEdge();
  const createNode = useCreateNode();
  const { data: allNodes } = useNodes();

  // Determine target node type for progressive filtering
  const targetNode = useMemo(
    () => allNodes?.find((n) => n.id === targetId),
    [allNodes, targetId],
  );
  const targetNodeType = targetNode?.node_type;

  // Fetch valid edge types based on schema rules
  const { data: validTypes } = useValidEdgeTypes(sourceNodeType, targetNodeType);

  const allEdgeTypeKeys = Object.keys(EDGE_TYPE_VOCABULARY);

  const filteredEdgeTypeKeys = useMemo(() => {
    if (!validTypes?.schema_active) return allEdgeTypeKeys;
    return allEdgeTypeKeys.filter((key) => validTypes.edge_type_ids.includes(key));
  }, [validTypes, allEdgeTypeKeys]);

  const edgeTypeOptions: SelectOption[] = filteredEdgeTypeKeys.map((key) => ({
    value: key,
    label: vocabEdgeLabel(key),
  }));

  const targetOptions: SelectOption[] = (allNodes ?? [])
    .filter((n) => n.id !== sourceNodeId)
    .map((n) => ({
      value: n.id,
      label: n.title,
      description: nodeLabel(n.node_type),
    }));

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

  // When target changes, clear edge type so user re-selects from filtered list
  const handleTargetChange = useCallback(
    (newTargetId: string) => {
      setTargetId(newTargetId);
      if (validTypes?.schema_active) {
        setEdgeType('');
      }
    },
    [validTypes],
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetId || !edgeType) return;

    await createEdge.mutateAsync({
      from_node_id: sourceNodeId,
      to_node_id: targetId,
      edge_type_id: edgeType,
      description: description.trim() || undefined,
    });

    setTargetId('');
    setEdgeType('');
    setDescription('');
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Verbinding toevoegen"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Annuleren
          </Button>
          <Button
            onClick={handleSubmit}
            loading={createEdge.isPending}
            disabled={!targetId || !edgeType}
          >
            Toevoegen
          </Button>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <CreatableSelect
          label="Doel-node"
          value={targetId}
          onChange={handleTargetChange}
          options={targetOptions}
          placeholder="Selecteer een node..."
          onCreate={handleCreateNode}
          createLabel="Nieuw aanmaken"
          required
        />

        <CreatableSelect
          label="Type verbinding"
          value={edgeType}
          onChange={setEdgeType}
          options={edgeTypeOptions}
          placeholder="Selecteer een type..."
          required
        />

        <Input
          label="Beschrijving (optioneel)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Toelichting op de verbinding..."
        />
      </form>
    </Modal>
  );
}
