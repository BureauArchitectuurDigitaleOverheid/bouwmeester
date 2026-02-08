import { useState, useCallback, useEffect } from 'react';
import { Trash2 } from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { Button } from '@/components/common/Button';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { RichTextEditor } from '@/components/common/RichTextEditor';
import { PersonQuickCreateForm } from '@/components/people/PersonQuickCreateForm';
import { useUpdateTask, useDeleteTask } from '@/hooks/useTasks';
import { useTaskFormOptions } from '@/hooks/useTaskFormOptions';
import {
  TaskStatus,
  TaskPriority,
  TASK_PRIORITY_LABELS,
  TASK_STATUS_LABELS,
} from '@/types';
import type { Task } from '@/types';
import type { SelectOption } from '@/components/common/CreatableSelect';

interface TaskEditFormProps {
  open: boolean;
  onClose: () => void;
  task: Task;
}

const priorityOptions: SelectOption[] = Object.values(TaskPriority).map((p) => ({
  value: p,
  label: TASK_PRIORITY_LABELS[p],
}));

const statusOptions: SelectOption[] = Object.values(TaskStatus).map((s) => ({
  value: s,
  label: TASK_STATUS_LABELS[s],
}));

export function TaskEditForm({ open, onClose, task }: TaskEditFormProps) {
  const [title, setTitle] = useState(task.title);
  const [description, setDescription] = useState(task.description ?? '');
  const [priority, setPriority] = useState<string>(task.priority);
  const [status, setStatus] = useState<string>(task.status);
  const [dueDate, setDueDate] = useState(task.due_date?.split('T')[0] ?? '');
  const [selectedNodeId, setSelectedNodeId] = useState(task.node_id ?? '');
  const [assigneeId, setAssigneeId] = useState(task.assignee_id ?? '');
  const [organisatieEenheidId, setOrganisatieEenheidId] = useState(task.organisatie_eenheid_id ?? '');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const updateTask = useUpdateTask();
  const deleteTaskMutation = useDeleteTask();
  const {
    nodeOptions, personOptions, eenheidOptions,
    handleCreateNode, handleCreatePerson,
    personCreateName, showPersonCreate, setShowPersonCreate,
  } = useTaskFormOptions();

  // Reset form when task changes
  useEffect(() => {
    setTitle(task.title);
    setDescription(task.description ?? '');
    setPriority(task.priority);
    setStatus(task.status);
    setDueDate(task.due_date?.split('T')[0] ?? '');
    setSelectedNodeId(task.node_id ?? '');
    setAssigneeId(task.assignee_id ?? '');
    setOrganisatieEenheidId(task.organisatie_eenheid_id ?? '');
    setShowDeleteConfirm(false);
  }, [task]);

  const handlePersonCreated = useCallback((personId: string) => {
    setAssigneeId(personId);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    await updateTask.mutateAsync({
      id: task.id,
      data: {
        title: title.trim(),
        description: description.trim() || undefined,
        priority: priority as TaskPriority,
        status: status as TaskStatus,
        due_date: dueDate || undefined,
        assignee_id: assigneeId || undefined,
        organisatie_eenheid_id: organisatieEenheidId || undefined,
      },
    });

    onClose();
  };

  const handleDelete = async () => {
    await deleteTaskMutation.mutateAsync(task.id);
    onClose();
  };

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title="Taak bewerken"
        footer={
          <div className="flex items-center justify-between w-full">
            <div>
              {showDeleteConfirm ? (
                <div className="flex items-center gap-2">
                  <span className="text-sm text-red-600">Weet je het zeker?</span>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={handleDelete}
                    loading={deleteTaskMutation.isPending}
                  >
                    Verwijderen
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowDeleteConfirm(false)}
                  >
                    Annuleren
                  </Button>
                </div>
              ) : (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowDeleteConfirm(true)}
                  icon={<Trash2 className="h-4 w-4" />}
                >
                  Verwijderen
                </Button>
              )}
            </div>
            <div className="flex items-center gap-3">
              <Button variant="secondary" onClick={onClose}>
                Annuleren
              </Button>
              <Button
                onClick={handleSubmit}
                loading={updateTask.isPending}
                disabled={!title.trim()}
              >
                Opslaan
              </Button>
            </div>
          </div>
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

          <div className="grid grid-cols-2 gap-4">
            <CreatableSelect
              label="Status"
              value={status}
              onChange={setStatus}
              options={statusOptions}
            />

            <CreatableSelect
              label="Prioriteit"
              value={priority}
              onChange={setPriority}
              options={priorityOptions}
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
