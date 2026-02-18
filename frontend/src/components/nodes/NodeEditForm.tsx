import { useState, useEffect } from 'react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { Select } from '@/components/common/Select';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { FormModalFooter } from '@/components/common/FormModalFooter';
import { RichTextFormField } from '@/components/common/RichTextFormField';
import { AutoTagDialog } from './AutoTagDialog';
import { DuplicateWarning } from './DuplicateWarning';
import { PendingTagsList } from './PendingTagsList';
import { TagSuggestions } from './TagSuggestions';
import { useUpdateNode } from '@/hooks/useNodes';
import { useNodeTypeOptions } from '@/hooks/useNodeTypeOptions';
import { useNodeTags, useAddTagToNode } from '@/hooks/useTags';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { useAutoTagSuggestion } from '@/hooks/useAutoTagSuggestion';
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

  const {
    showAutoTagDialog, autoTagMatched, autoTagNew,
    checkAndSuggest, closeAutoTagDialog,
  } = useAutoTagSuggestion();

  useEffect(() => {
    setTitle(node.title);
    setNodeType(node.node_type);
    setDescription(node.description ?? '');
    setStatus(node.status ?? '');
  }, [node]);

  const doSave = async (extraTags: { name: string; isNew: boolean }[] = []) => {
    const allTags = [...pendingTags, ...extraTags];

    await updateNode.mutateAsync({
      id: node.id,
      data: {
        title: title.trim(),
        description: description.trim() || undefined,
        status: status.trim() || undefined,
      },
      actorId: currentPerson?.id,
    });

    for (const tag of allTags) {
      try {
        await addTag.mutateAsync({ nodeId: node.id, data: { tag_name: tag.name } });
      } catch {
        // Non-critical: tag may already exist
      }
    }

    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    const existingTagNames = nodeTags?.map((nt) => nt.tag.name) ?? [];
    const shown = await checkAndSuggest({
      title,
      description,
      nodeType,
      currentTagCount: (nodeTags?.length ?? 0) + pendingTags.length,
      existingTagNames,
      pendingTagNames: pendingTags.map((t) => t.name),
    });
    if (!shown) doSave();
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

        <DuplicateWarning title={title} excludeNodeId={node.id} />

        <CreatableSelect
          label="Type"
          value={nodeType}
          onChange={setNodeType}
          options={nodeTypeOptions}
          disabled
        />

        <RichTextFormField label="Beschrijving" value={description} onChange={setDescription} rows={4} />

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

        <PendingTagsList
          tags={pendingTags}
          onRemove={(name) => setPendingTags((prev) => prev.filter((t) => t.name !== name))}
        />

        <Select
          label="Status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          options={Object.entries(NODE_STATUS_LABELS).map(([value, label]) => ({ value, label }))}
        />
      </form>

      <AutoTagDialog
        open={showAutoTagDialog}
        onClose={closeAutoTagDialog}
        matchedTags={autoTagMatched}
        suggestedNewTags={autoTagNew}
        onAccept={(tags) => doSave(tags)}
        onSkip={() => doSave()}
      />
    </Modal>
  );
}
