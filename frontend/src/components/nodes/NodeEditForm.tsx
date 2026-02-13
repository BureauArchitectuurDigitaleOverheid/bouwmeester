import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { Select } from '@/components/common/Select';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { FormModalFooter } from '@/components/common/FormModalFooter';
import { RichTextEditor } from '@/components/common/RichTextEditor';
import { TagSuggestions } from './TagSuggestions';
import { useUpdateNode } from '@/hooks/useNodes';
import { useNodeTypeOptions } from '@/hooks/useNodeTypeOptions';
import { useNodeTags, useAddTagToNode } from '@/hooks/useTags';
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
  const [pendingTags, setPendingTags] = useState<{ name: string; isNew: boolean }[]>([]);
  const updateNode = useUpdateNode();
  const { data: nodeTags } = useNodeTags(node.id);
  const addTag = useAddTagToNode();

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

    // Apply suggested tags
    for (const tag of pendingTags) {
      addTag.mutate({ nodeId: node.id, data: { tag_name: tag.name } });
    }

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
            placeholder="Optionele beschrijving... Gebruik @ voor personen, # voor nodes/taken, **vet** voor opmaak"
            rows={4}
          />
        </div>

        <TagSuggestions
          title={title}
          description={description}
          nodeType={nodeType}
          existingTagNames={nodeTags?.map((nt) => nt.tag.name) ?? []}
          onAcceptTag={(tagName, isNew) => {
            setPendingTags((prev) => {
              if (prev.some((t) => t.name === tagName)) return prev;
              return [...prev, { name: tagName, isNew }];
            });
          }}
        />

        {pendingTags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {pendingTags.map((tag) => (
              <span
                key={tag.name}
                className="inline-flex items-center gap-1 rounded-full bg-green-100 text-green-700 px-2.5 py-0.5 text-xs font-medium"
              >
                {tag.name}
                <button
                  type="button"
                  onClick={() => setPendingTags((prev) => prev.filter((t) => t.name !== tag.name))}
                  className="hover:text-red-500 transition-colors ml-0.5"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
        )}

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
