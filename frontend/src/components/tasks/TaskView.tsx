import { useState, useMemo, useCallback } from 'react';
import { Plus, LayoutList, Columns3 } from 'lucide-react';
import { Button } from '@/components/common/Button';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { TaskList } from './TaskList';
import { TaskBoard } from './TaskBoard';
import { TaskCreateForm } from './TaskCreateForm';
import { usePeople } from '@/hooks/usePeople';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import {
  TaskStatus,
  TaskPriority,
  TASK_STATUS_LABELS,
  TASK_PRIORITY_LABELS,
} from '@/types';
import type { Task } from '@/types';
import type { SelectOption } from '@/components/common/CreatableSelect';

type ViewMode = 'list' | 'board';

const VIEW_STORAGE_KEY = 'tasks-view-mode';
const MY_TASKS_SENTINEL = '__me__';

function getStoredView(): ViewMode {
  const stored = localStorage.getItem(VIEW_STORAGE_KEY);
  return stored === 'board' ? 'board' : 'list';
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

  const { data: people } = usePeople();
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
      description: p.functie ?? undefined,
    })),
  ], [people, currentPerson]);

  const handleViewChange = (mode: ViewMode) => {
    setViewMode(mode);
    localStorage.setItem(VIEW_STORAGE_KEY, mode);
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
      return true;
    });
  }, [tasks, statusFilter, priorityFilter, personFilter, currentPerson]);

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        {/* Left: Filters */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="w-44">
            <CreatableSelect
              value={statusFilter}
              onChange={setStatusFilter}
              options={statusOptions}
              placeholder="Alle statussen"
            />
          </div>

          <div className="w-44">
            <CreatableSelect
              value={priorityFilter}
              onChange={setPriorityFilter}
              options={priorityOptions}
              placeholder="Alle prioriteiten"
            />
          </div>

          <div className="w-52">
            <CreatableSelect
              value={personFilter}
              onChange={setPersonFilter}
              options={personOptions}
              placeholder="Alle personen"
            />
          </div>
        </div>

        {/* Right: View toggle + New task */}
        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-xl border border-border bg-white p-0.5">
            <button
              onClick={() => handleViewChange('list')}
              className={`p-1.5 rounded-lg transition-colors ${
                viewMode === 'list'
                  ? 'bg-primary-900 text-white'
                  : 'text-text-secondary hover:text-text'
              }`}
              title="Lijstweergave"
            >
              <LayoutList className="h-4 w-4" />
            </button>
            <button
              onClick={() => handleViewChange('board')}
              className={`p-1.5 rounded-lg transition-colors ${
                viewMode === 'board'
                  ? 'bg-primary-900 text-white'
                  : 'text-text-secondary hover:text-text'
              }`}
              title="Bordweergave"
            >
              <Columns3 className="h-4 w-4" />
            </button>
          </div>

          <Button
            size="sm"
            icon={<Plus className="h-4 w-4" />}
            onClick={() => setShowCreateForm(true)}
          >
            Nieuwe taak
          </Button>
        </div>
      </div>

      {/* Content */}
      {viewMode === 'list' ? (
        <TaskList tasks={filteredTasks} onEditTask={handleTaskClick} />
      ) : (
        <TaskBoard tasks={filteredTasks} onEditTask={handleTaskClick} />
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
