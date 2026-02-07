import { useState } from 'react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { Button } from '@/components/common/Button';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { useCreateNode } from '@/hooks/useNodes';
import { NodeType, NODE_TYPE_LABELS } from '@/types';
import type { SelectOption } from '@/components/common/CreatableSelect';

interface NodeCreateFormProps {
  open: boolean;
  onClose: () => void;
}

const nodeTypeOptions: SelectOption[] = Object.values(NodeType).map((type) => ({
  value: type,
  label: NODE_TYPE_LABELS[type],
}));

export function NodeCreateForm({ open, onClose }: NodeCreateFormProps) {
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
        <>
          <Button variant="secondary" onClick={onClose}>
            Annuleren
          </Button>
          <Button
            onClick={handleSubmit}
            loading={createNode.isPending}
            disabled={!title.trim()}
          >
            Aanmaken
          </Button>
        </>
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
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Optionele beschrijving..."
            rows={4}
            className="block w-full rounded-xl border border-border bg-white px-3.5 py-2.5 text-sm text-text placeholder:text-text-secondary/50 transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 hover:border-border-hover resize-none"
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
