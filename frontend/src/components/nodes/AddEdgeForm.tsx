import { useState, useCallback } from 'react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { Button } from '@/components/common/Button';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { useCreateEdge } from '@/hooks/useEdges';
import { useNodes, useCreateNode } from '@/hooks/useNodes';
import { NodeType, NODE_TYPE_LABELS } from '@/types';
import type { SelectOption } from '@/components/common/CreatableSelect';

interface AddEdgeFormProps {
  open: boolean;
  onClose: () => void;
  sourceNodeId: string;
}

const edgeTypeOptions: SelectOption[] = [
  { value: 'kadert', label: 'Kadert in' },
  { value: 'draagt_bij_aan', label: 'Draagt bij aan' },
  { value: 'implementeert', label: 'Implementeert' },
  { value: 'vereist', label: 'Vereist' },
  { value: 'aanvulling_op', label: 'Aanvulling op' },
  { value: 'conflicteert_met', label: 'Conflicteert met' },
  { value: 'vervangt', label: 'Vervangt' },
];

export function AddEdgeForm({ open, onClose, sourceNodeId }: AddEdgeFormProps) {
  const [targetId, setTargetId] = useState('');
  const [edgeType, setEdgeType] = useState('');
  const [description, setDescription] = useState('');
  const createEdge = useCreateEdge();
  const createNode = useCreateNode();
  const { data: allNodes } = useNodes();

  const targetOptions: SelectOption[] = (allNodes ?? [])
    .filter((n) => n.id !== sourceNodeId)
    .map((n) => ({
      value: n.id,
      label: n.title,
      description: NODE_TYPE_LABELS[n.node_type],
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
          onChange={setTargetId}
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
