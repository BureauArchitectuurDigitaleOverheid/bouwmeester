import { useState, useMemo, useCallback } from 'react';
import { Plus, LayoutList, Columns3, User } from 'lucide-react';
import { Button } from '@/components/common/Button';
import { ViewToggle } from '@/components/common/ViewToggle';
import type { ViewToggleOption } from '@/components/common/ViewToggle';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { TaskList } from './TaskList';
import { TaskBoard } from './TaskBoard';
import { TaskPersonalView } from './TaskPersonalView';
import { TaskCreateForm } from './TaskCreateForm';
import { usePeople } from '@/hooks/usePeople';
import { useOrganisatieFlat } from '@/hooks/useOrganisatie';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import {
  TaskStatus,
  TaskPriority,
  TASK_STATUS_LABELS,
  TASK_PRIORITY_LABELS,
  formatOrganisatieType,
  formatFunctie,
} from '@/types';
import type { Task } from '@/types';
import type { SelectOption } from '@/components/common/CreatableSelect';

type ViewMode = 'list' | 'board' | 'personal';

const VIEW_OPTIONS: ViewToggleOption<ViewMode>[] = [
  { value: 'list', label: 'Lijst', icon: <LayoutList className="h-3.5 w-3.5" /> },
  { value: 'board', label: 'Bord', icon: <Columns3 className="h-3.5 w-3.5" /> },
  { value: 'personal', label: 'Persoonlijk', icon: <User className="h-3.5 w-3.5" /> },
];

const VIEW_STORAGE_KEY = 'tasks-view-mode';
const MY_TASKS_SENTINEL = '__me__';

function getStoredView(): ViewMode {
  try {
    const stored = localStorage.getItem(VIEW_STORAGE_KEY);
    if (stored === 'board' || stored === 'personal') return stored;
  } catch {
    // localStorage unavailable (e.g. private browsing).
  }
  return 'list';
}

const statusOptions: SelectOption[] = [
  { value: '', label: 'Alle statussen' },
  ...Object.values(TaskStatus).map((s) => ({
    value: s,
    label: TASK_STATUS_LABELS[s],
  })),
];

const priorityOptions: SelectOption[] = [
  { value: '', label: 'Alle prioriteiten' },
  ...Object.values(TaskPriority).map((p) => ({
    value: p,
    label: TASK_PRIORITY_LABELS[p],
  })),
];

interface TaskViewProps {
  tasks: Task[];
  /** Pre-set node_id when creating a new task from within a node */
  defaultNodeId?: string;
}

export function TaskView({ tasks, defaultNodeId }: TaskViewProps) {
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>(getStoredView);
  const { openTaskDetail } = useTaskDetail();
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [priorityFilter, setPriorityFilter] = useState<string>('');
  const [personFilter, setPersonFilter] = useState<string>('');
  const [eenheidFilter, setEenheidFilter] = useState<string>('');

  const { data: people } = usePeople();
  const { data: eenheden } = useOrganisatieFlat();
  const { currentPerson } = useCurrentPerson();

  const personOptions: SelectOption[] = useMemo(() => [
    { value: '', label: 'Alle personen' },
    ...(currentPerson
      ? [{
          value: MY_TASKS_SENTINEL,
          label: `Mijn taken (${currentPerson.naam})`,
        }]
      : []),
    ...(people ?? []).map((p) => ({
      value: p.id,
      label: p.naam,
      description: formatFunctie(p.functie),
    })),
  ], [people, currentPerson]);

  const eenheidOptions: SelectOption[] = useMemo(() => [
    { value: '', label: 'Alle eenheden' },
    ...(eenheden ?? []).map((e) => ({
      value: e.id,
      label: e.naam,
      description: formatOrganisatieType(e.type),
    })),
  ], [eenheden]);

  const handleViewChange = (mode: ViewMode) => {
    setViewMode(mode);
    try {
      localStorage.setItem(VIEW_STORAGE_KEY, mode);
    } catch {
      // localStorage unavailable (e.g. private browsing).
    }
  };

  const handleTaskClick = useCallback((task: Task) => {
    openTaskDetail(task.id);
  }, [openTaskDetail]);

  const filteredTasks = useMemo(() => {
    const effectivePersonId = personFilter === MY_TASKS_SENTINEL
      ? currentPerson?.id ?? null
      : personFilter || null;
    return tasks.filter((task) => {
      if (statusFilter && task.status !== statusFilter) return false;
      if (priorityFilter && task.priority !== priorityFilter) return false;
      if (effectivePersonId && task.assignee_id !== effectivePersonId) return false;
      if (eenheidFilter && task.organisatie_eenheid_id !== eenheidFilter) return false;
      return true;
    });
  }, [tasks, statusFilter, priorityFilter, personFilter, eenheidFilter, currentPerson]);

  return (
    <div className="space-y-6">
      {/* Toolbar */}
      <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-3">
        {/* View toggle + New task (above filters on mobile/tablet, right on xl) */}
        <div className="flex items-center gap-2 shrink-0 order-first xl:order-last">
          <ViewToggle value={viewMode} onChange={handleViewChange} options={VIEW_OPTIONS} />

          <Button
            icon={<Plus className="h-4 w-4" />}
            onClick={() => setShowCreateForm(true)}
          >
            <span className="hidden sm:inline">Nieuwe taak</span>
          </Button>
        </div>

        {/* Filters */}
        <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-center sm:gap-3">
          <div className="w-full sm:w-44">
            <CreatableSelect
              value={statusFilter}
              onChange={setStatusFilter}
              options={statusOptions}
              placeholder="Alle statussen"
              searchable={false}
            />
          </div>

          <div className="w-full sm:w-44">
            <CreatableSelect
              value={priorityFilter}
              onChange={setPriorityFilter}
              options={priorityOptions}
              placeholder="Alle prioriteiten"
              searchable={false}
            />
          </div>

          <div className="w-full sm:w-52">
            <CreatableSelect
              value={personFilter}
              onChange={setPersonFilter}
              options={personOptions}
              placeholder="Alle personen"
            />
          </div>

          <div className="w-full sm:w-52">
            <CreatableSelect
              value={eenheidFilter}
              onChange={setEenheidFilter}
              options={eenheidOptions}
              placeholder="Alle eenheden"
            />
          </div>
        </div>
      </div>

      {/* Content */}
      {viewMode === 'list' ? (
        <TaskList tasks={filteredTasks} onEditTask={handleTaskClick} />
      ) : viewMode === 'board' ? (
        <TaskBoard tasks={filteredTasks} onEditTask={handleTaskClick} />
      ) : (
        <TaskPersonalView tasks={filteredTasks} onEditTask={handleTaskClick} />
      )}

      {/* Create form modal */}
      <TaskCreateForm
        open={showCreateForm}
        onClose={() => setShowCreateForm(false)}
        nodeId={defaultNodeId}
      />
    </div>
  );
}
