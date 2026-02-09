import { useState, useEffect } from 'react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { Select } from '@/components/common/Select';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { FormModalFooter } from '@/components/common/FormModalFooter';
import { RichTextEditor } from '@/components/common/RichTextEditor';
import { useUpdateNode } from '@/hooks/useNodes';
import { useNodeTypeOptions } from '@/hooks/useNodeTypeOptions';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { NODE_STATUS_LABELS } from '@/types';
import type { CorpusNode } from '@/types';

interface NodeEditFormProps {
  open: boolean;
  onClose: () => void;
  node: CorpusNode;
}

export function NodeEditForm({ open, onClose, node }: NodeEditFormProps) {
  const nodeTypeOptions = useNodeTypeOptions();
  const { currentPerson } = useCurrentPerson();

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
      actorId: currentPerson?.id,
    });

    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Node bewerken"
      footer={
        <FormModalFooter
          onCancel={onClose}
          onSubmit={handleSubmit}
          submitLabel="Opslaan"
          isLoading={updateNode.isPending}
          disabled={!title.trim()}
        />
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

        <Select
          label="Status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          options={Object.entries(NODE_STATUS_LABELS).map(([value, label]) => ({ value, label }))}
        />
      </form>
    </Modal>
  );
}
