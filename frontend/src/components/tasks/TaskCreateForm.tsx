import { useState, useCallback, useEffect } from 'react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { FormModalFooter } from '@/components/common/FormModalFooter';
import { RichTextEditor } from '@/components/common/RichTextEditor';
import { PersonQuickCreateForm } from '@/components/people/PersonQuickCreateForm';
import { useCreateTask } from '@/hooks/useTasks';
import { useTaskFormOptions } from '@/hooks/useTaskFormOptions';
import { useEnumOptions } from '@/hooks/useEnumOptions';
import {
  TaskPriority,
  TASK_PRIORITY_LABELS,
} from '@/types';

interface TaskCreateFormProps {
  open: boolean;
  onClose: () => void;
  nodeId?: string;
  parentId?: string;
}

export function TaskCreateForm({ open, onClose, nodeId, parentId }: TaskCreateFormProps) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<string>(TaskPriority.NORMAAL);
  const [dueDate, setDueDate] = useState('');
  const [selectedNodeId, setSelectedNodeId] = useState(nodeId ?? '');
  const [assigneeId, setAssigneeId] = useState('');
  const [organisatieEenheidId, setOrganisatieEenheidId] = useState('');

  const priorityOptions = useEnumOptions(TaskPriority, TASK_PRIORITY_LABELS);

  // Reset form state when dialog opens
  useEffect(() => {
    if (open) {
      setTitle('');
      setDescription('');
      setPriority(TaskPriority.NORMAAL);
      setDueDate('');
      setSelectedNodeId(nodeId ?? '');
      setAssigneeId('');
      setOrganisatieEenheidId('');
    }
  }, [open, nodeId]);

  const createTask = useCreateTask();
  const {
    nodeOptions, personOptions, eenheidOptions,
    handleCreateNode, handleCreatePerson,
    personCreateName, showPersonCreate, setShowPersonCreate,
  } = useTaskFormOptions();

  const handlePersonCreated = useCallback((personId: string) => {
    setAssigneeId(personId);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || (!selectedNodeId && !parentId)) return;

    await createTask.mutateAsync({
      title: title.trim(),
      description: description.trim() || undefined,
      priority: priority as TaskPriority,
      due_date: dueDate || undefined,
      node_id: selectedNodeId || nodeId || '',
      assignee_id: assigneeId || undefined,
      organisatie_eenheid_id: organisatieEenheidId || undefined,
      parent_id: parentId || undefined,
    });

    onClose();
  };

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={parentId ? 'Subtaak aanmaken' : 'Nieuwe taak aanmaken'}
        footer={
          <FormModalFooter
            onCancel={onClose}
            onSubmit={handleSubmit}
            submitLabel="Aanmaken"
            isLoading={createTask.isPending}
            disabled={!title.trim() || (!selectedNodeId && !parentId)}
          />
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
            required={!parentId}
            error={!selectedNodeId && !parentId && createTask.isError ? 'Node is verplicht' : undefined}
          />

          <CreatableSelect
            label="Verantwoordelijke eenheid"
            value={organisatieEenheidId}
            onChange={setOrganisatieEenheidId}
            options={eenheidOptions}
            placeholder="Selecteer een eenheid..."
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
