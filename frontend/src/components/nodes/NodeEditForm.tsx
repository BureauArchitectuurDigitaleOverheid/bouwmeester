import { useState, useEffect } from 'react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { Button } from '@/components/common/Button';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { RichTextEditor } from '@/components/common/RichTextEditor';
import { useUpdateNode } from '@/hooks/useNodes';
import { NodeType } from '@/types';
import type { CorpusNode } from '@/types';
import type { SelectOption } from '@/components/common/CreatableSelect';
import { useVocabulary } from '@/contexts/VocabularyContext';

interface NodeEditFormProps {
  open: boolean;
  onClose: () => void;
  node: CorpusNode;
}

export function NodeEditForm({ open, onClose, node }: NodeEditFormProps) {
  const { nodeLabel } = useVocabulary();
  const nodeTypeOptions: SelectOption[] = Object.values(NodeType).map((type) => ({
    value: type,
    label: nodeLabel(type),
  }));

  const [title, setTitle] = useState(node.title);
  const [nodeType, setNodeType] = useState<string>(node.node_type);
  const [description, setDescription] = useState(node.description ?? '');
  const [status, setStatus] = useState(node.status ?? '');
  const updateNode = useUpdateNode();

  useEffect(() => {
    setTitle(node.title);
    setNodeType(node.node_type);
    setDescription(node.description ?? '');
    setStatus(node.status ?? '');
  }, [node]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    await updateNode.mutateAsync({
      id: node.id,
      data: {
        title: title.trim(),
        description: description.trim() || undefined,
        status: status.trim() || undefined,
      },
    });

    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Node bewerken"
      footer={
        <div className="flex items-center justify-end w-full gap-3">
          <Button variant="secondary" onClick={onClose}>
            Annuleren
          </Button>
          <Button
            onClick={handleSubmit}
            loading={updateNode.isPending}
            disabled={!title.trim()}
          >
            Opslaan
          </Button>
        </div>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Titel"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Voer een titel in..."
          required
          autoFocus
        />

        <CreatableSelect
          label="Type"
          value={nodeType}
          onChange={setNodeType}
          options={nodeTypeOptions}
          disabled
        />

        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-text">
            Beschrijving
          </label>
          <RichTextEditor
            value={description}
            onChange={setDescription}
            placeholder="Optionele beschrijving... Gebruik @ voor personen, # voor nodes/taken"
            rows={4}
          />
        </div>

        <Input
          label="Status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          placeholder="Bijv. concept, actief, afgerond..."
        />
      </form>
    </Modal>
  );
}
