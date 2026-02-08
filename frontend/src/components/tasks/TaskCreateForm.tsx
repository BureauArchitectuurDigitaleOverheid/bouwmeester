import { useState, useCallback } from 'react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { Button } from '@/components/common/Button';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { RichTextEditor } from '@/components/common/RichTextEditor';
import { PersonQuickCreateForm } from '@/components/people/PersonQuickCreateForm';
import { useCreateTask } from '@/hooks/useTasks';
import { useNodes, useCreateNode } from '@/hooks/useNodes';
import { usePeople } from '@/hooks/usePeople';
import {
  TaskPriority,
  TASK_PRIORITY_LABELS,
  NodeType,
} from '@/types';
import { useVocabulary } from '@/contexts/VocabularyContext';
import type { SelectOption } from '@/components/common/CreatableSelect';

interface TaskCreateFormProps {
  open: boolean;
  onClose: () => void;
  nodeId?: string;
}

const priorityOptions: SelectOption[] = Object.values(TaskPriority).map((p) => ({
  value: p,
  label: TASK_PRIORITY_LABELS[p],
}));

export function TaskCreateForm({ open, onClose, nodeId }: TaskCreateFormProps) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<string>(TaskPriority.NORMAAL);
  const [dueDate, setDueDate] = useState('');
  const [selectedNodeId, setSelectedNodeId] = useState(nodeId ?? '');
  const [assigneeId, setAssigneeId] = useState('');
  const [personCreateName, setPersonCreateName] = useState('');
  const [showPersonCreate, setShowPersonCreate] = useState(false);

  const { nodeLabel } = useVocabulary();
  const createTask = useCreateTask();
  const createNode = useCreateNode();
  const { data: allNodes } = useNodes();
  const { data: allPeople } = usePeople();

  const nodeOptions: SelectOption[] = (allNodes ?? []).map((n) => ({
    value: n.id,
    label: n.title,
    description: nodeLabel(n.node_type),
  }));

  const personOptions: SelectOption[] = (allPeople ?? []).map((p) => ({
    value: p.id,
    label: p.naam,
    description: p.functie ?? p.afdeling ?? undefined,
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

  const handleCreatePerson = useCallback(
    async (text: string): Promise<string | null> => {
      setPersonCreateName(text);
      setShowPersonCreate(true);
      return null; // Person will be selected via the dialog callback
    },
    [],
  );

  const handlePersonCreated = useCallback((personId: string) => {
    setAssigneeId(personId);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !selectedNodeId) return;

    await createTask.mutateAsync({
      title: title.trim(),
      description: description.trim() || undefined,
      priority: priority as TaskPriority,
      due_date: dueDate || undefined,
      node_id: selectedNodeId,
      assignee_id: assigneeId || undefined,
    });

    setTitle('');
    setDescription('');
    setPriority(TaskPriority.NORMAAL);
    setDueDate('');
    setSelectedNodeId(nodeId ?? '');
    setAssigneeId('');
    onClose();
  };

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title="Nieuwe taak aanmaken"
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>
              Annuleren
            </Button>
            <Button
              onClick={handleSubmit}
              loading={createTask.isPending}
              disabled={!title.trim() || !selectedNodeId}
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
            placeholder="Wat moet er gebeuren?"
            required
            autoFocus
          />

          <div className="space-y-1.5">
            <label className="block text-sm font-medium text-text">
              Beschrijving
            </label>
            <RichTextEditor
              value={description}
              onChange={setDescription}
              placeholder="Optionele beschrijving... Gebruik @ voor personen, # voor nodes/taken"
              rows={3}
            />
          </div>

          <CreatableSelect
            label="Node"
            value={selectedNodeId}
            onChange={setSelectedNodeId}
            options={nodeOptions}
            placeholder="Koppel aan een node..."
            onCreate={handleCreateNode}
            createLabel="Nieuw aanmaken"
            required
            error={!selectedNodeId && createTask.isError ? 'Node is verplicht' : undefined}
          />

          <CreatableSelect
            label="Toegewezen aan"
            value={assigneeId}
            onChange={setAssigneeId}
            options={personOptions}
            placeholder="Selecteer een persoon..."
            onCreate={handleCreatePerson}
            createLabel="Nieuw aanmaken"
          />

          <CreatableSelect
            label="Prioriteit"
            value={priority}
            onChange={setPriority}
            options={priorityOptions}
          />

          <Input
            label="Deadline"
            type="date"
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
          />
        </form>
      </Modal>

      <PersonQuickCreateForm
        open={showPersonCreate}
        onClose={() => setShowPersonCreate(false)}
        initialName={personCreateName}
        onCreated={handlePersonCreated}
      />
    </>
  );
}
