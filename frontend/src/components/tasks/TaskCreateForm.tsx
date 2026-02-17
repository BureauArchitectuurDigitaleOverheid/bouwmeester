import { useState, useCallback, useEffect, useRef } from 'react';
import { Sparkles, Loader2 } from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { FormModalFooter } from '@/components/common/FormModalFooter';
import { RichTextFormField } from '@/components/common/RichTextFormField';
import { PersonQuickCreateForm } from '@/components/people/PersonQuickCreateForm';
import { useCreateTask, useWorkTypes } from '@/hooks/useTasks';
import { useOpdrachten } from '@/hooks/useOpdrachten';
import { useTaskFormOptions } from '@/hooks/useTaskFormOptions';
import { useEnumOptions } from '@/hooks/useEnumOptions';
import { suggestTask } from '@/api/llm';
import {
  TaskPriority,
  TASK_PRIORITY_LABELS,
} from '@/types';

interface TaskCreateFormProps {
  open: boolean;
  onClose: () => void;
  nodeId?: string;
  parentId?: string;
  opdrachtId?: string;
  /** Pre-fill context from a node (C1: Smart Task Creation) */
  nodeTitle?: string;
  nodeDescription?: string;
  nodeType?: string;
  /** Stakeholder person IDs in order: eigenaar first, then betrokken */
  stakeholderPersonIds?: string[];
}

export function TaskCreateForm({
  open,
  onClose,
  nodeId,
  parentId,
  opdrachtId,
  nodeTitle,
  nodeDescription,
  nodeType,
  stakeholderPersonIds,
}: TaskCreateFormProps) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<string>(TaskPriority.NORMAAL);
  const [dueDate, setDueDate] = useState('');
  const [selectedNodeId, setSelectedNodeId] = useState(nodeId ?? '');
  const [assigneeId, setAssigneeId] = useState('');
  const [organisatieEenheidId, setOrganisatieEenheidId] = useState('');
  const [workType, setWorkType] = useState('');
  const [selectedOpdrachtId, setSelectedOpdrachtId] = useState(opdrachtId ?? '');
  const [aiLoading, setAiLoading] = useState(false);
  const userTypedRef = useRef(false);

  const priorityOptions = useEnumOptions(TaskPriority, TASK_PRIORITY_LABELS);
  const { data: workTypes = [] } = useWorkTypes();
  const workTypeOptions = workTypes.map((wt) => ({ value: wt, label: wt }));
  const { data: opdrachten = [] } = useOpdrachten();
  const opdrachtOptions = opdrachten.map((o) => ({ value: o.id, label: o.titel, description: o.type }));

  // Reset form state when dialog opens + AI suggestion
  useEffect(() => {
    if (open) {
      setTitle('');
      setDescription('');
      setPriority(TaskPriority.NORMAAL);
      setDueDate('');
      setSelectedNodeId(nodeId ?? '');
      setAssigneeId('');
      setOrganisatieEenheidId('');
      setWorkType('');
      setSelectedOpdrachtId(opdrachtId ?? '');
      userTypedRef.current = false;
      setAiLoading(false);

      // Pre-select assignee from stakeholders
      if (stakeholderPersonIds && stakeholderPersonIds.length > 0) {
        setAssigneeId(stakeholderPersonIds[0]);
      }

      // AI task suggestion
      if (nodeTitle) {
        setAiLoading(true);
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 3000);
        suggestTask(nodeTitle, nodeDescription, nodeType)
          .then((res) => {
            clearTimeout(timeout);
            if (!userTypedRef.current && res.available) {
              if (res.title) setTitle(res.title);
              if (res.description) setDescription(res.description);
            }
          })
          .catch(() => {
            clearTimeout(timeout);
          })
          .finally(() => setAiLoading(false));
      }
    }
  }, [open, nodeId, opdrachtId, nodeTitle, nodeDescription, nodeType, stakeholderPersonIds]);

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
      opdracht_id: selectedOpdrachtId || undefined,
      work_type: workType.trim() || undefined,
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
          <div>
            <div className="flex items-center gap-1.5 mb-1">
              <label className="block text-sm font-medium text-text">Titel</label>
              {aiLoading && (
                <span className="inline-flex items-center gap-1 text-xs text-text-secondary">
                  <Sparkles className="h-3 w-3 text-amber-500" />
                  <Loader2 className="h-3 w-3 animate-spin" />
                </span>
              )}
            </div>
            <Input
              value={title}
              onChange={(e) => {
                userTypedRef.current = true;
                setTitle(e.target.value);
              }}
              placeholder="Wat moet er gebeuren?"
              required
              autoFocus
            />
          </div>

          <RichTextFormField label="Beschrijving" value={description} onChange={setDescription} />

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
            searchable={false}
          />

          <CreatableSelect
            label="Werktype"
            value={workType}
            onChange={setWorkType}
            options={workTypeOptions}
            placeholder="bijv. Analyse, Overleg, Review..."
            onCreate={async (text) => { setWorkType(text); return text; }}
            createLabel="Nieuw werktype"
            onClear={() => setWorkType('')}
          />

          <CreatableSelect
            label="Opdracht"
            value={selectedOpdrachtId}
            onChange={setSelectedOpdrachtId}
            options={opdrachtOptions}
            placeholder="Koppel aan een opdracht..."
            onClear={() => setSelectedOpdrachtId('')}
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
