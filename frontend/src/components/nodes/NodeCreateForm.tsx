import { useState } from 'react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { FormModalFooter } from '@/components/common/FormModalFooter';
import { RichTextEditor } from '@/components/common/RichTextEditor';
import { useCreateNode } from '@/hooks/useNodes';
import { useNodeTypeOptions } from '@/hooks/useNodeTypeOptions';
import { NodeType } from '@/types';

interface NodeCreateFormProps {
  open: boolean;
  onClose: () => void;
}

export function NodeCreateForm({ open, onClose }: NodeCreateFormProps) {
  const nodeTypeOptions = useNodeTypeOptions();
  const [title, setTitle] = useState('');
  const [nodeType, setNodeType] = useState<string>(NodeType.DOSSIER);
  const [description, setDescription] = useState('');
  const [status, setStatus] = useState('');
  const createNode = useCreateNode();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    await createNode.mutateAsync({
      title: title.trim(),
      node_type: nodeType as NodeType,
      description: description.trim() || undefined,
      status: status.trim() || undefined,
    });

    // Reset form
    setTitle('');
    setNodeType(NodeType.DOSSIER);
    setDescription('');
    setStatus('');
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Nieuwe node aanmaken"
      footer={
        <FormModalFooter
          onCancel={onClose}
          onSubmit={handleSubmit}
          submitLabel="Aanmaken"
          isLoading={createNode.isPending}
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
