import { useState, useMemo } from 'react';
import { Plus, LayoutList, Columns3 } from 'lucide-react';
import { Button } from '@/components/common/Button';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { TaskList } from '@/components/tasks/TaskList';
import { TaskBoard } from '@/components/tasks/TaskBoard';
import { TaskCreateForm } from '@/components/tasks/TaskCreateForm';
import { TaskEditForm } from '@/components/tasks/TaskEditForm';
import { useTasks } from '@/hooks/useTasks';
import { usePeople } from '@/hooks/usePeople';
import {
  TaskStatus,
  TaskPriority,
  TASK_STATUS_LABELS,
  TASK_PRIORITY_LABELS,
} from '@/types';
import type { Task } from '@/types';

type ViewMode = 'list' | 'board';

const VIEW_STORAGE_KEY = 'tasks-view-mode';

function getStoredView(): ViewMode {
  const stored = localStorage.getItem(VIEW_STORAGE_KEY);
  return stored === 'board' ? 'board' : 'list';
}

export function TasksPage() {
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>(getStoredView);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [priorityFilter, setPriorityFilter] = useState<string>('');
  const [personFilter, setPersonFilter] = useState<string>('');

  const { data: tasks, isLoading } = useTasks();
  const { data: people } = usePeople();

  const handleViewChange = (mode: ViewMode) => {
    setViewMode(mode);
    localStorage.setItem(VIEW_STORAGE_KEY, mode);
  };

  const filteredTasks = useMemo(() => {
    if (!tasks) return [];
    return tasks.filter((task) => {
      if (statusFilter && task.status !== statusFilter) return false;
      if (priorityFilter && task.priority !== priorityFilter) return false;
      if (personFilter && task.assignee_id !== personFilter) return false;
      return true;
    });
  }, [tasks, statusFilter, priorityFilter, personFilter]);

  return (
    <div className="space-y-6">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        {/* Left: Filters */}
        <div className="flex items-center gap-3 flex-wrap">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-xl border border-border bg-white px-3 py-2 text-sm text-text hover:border-border-hover focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 transition-colors"
          >
            <option value="">Alle statussen</option>
            {Object.values(TaskStatus).map((s) => (
              <option key={s} value={s}>
                {TASK_STATUS_LABELS[s]}
              </option>
            ))}
          </select>

          <select
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value)}
            className="rounded-xl border border-border bg-white px-3 py-2 text-sm text-text hover:border-border-hover focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 transition-colors"
          >
            <option value="">Alle prioriteiten</option>
            {Object.values(TaskPriority).map((p) => (
              <option key={p} value={p}>
                {TASK_PRIORITY_LABELS[p]}
              </option>
            ))}
          </select>

          <select
            value={personFilter}
            onChange={(e) => setPersonFilter(e.target.value)}
            className="rounded-xl border border-border bg-white px-3 py-2 text-sm text-text hover:border-border-hover focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 transition-colors"
          >
            <option value="">Alle personen</option>
            {(people ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.naam}
              </option>
            ))}
          </select>
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
            icon={<Plus className="h-4 w-4" />}
            onClick={() => setShowCreateForm(true)}
          >
            Nieuwe taak
          </Button>
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <LoadingSpinner className="py-8" />
      ) : viewMode === 'list' ? (
        <TaskList tasks={filteredTasks} onEditTask={setEditingTask} />
      ) : (
        <TaskBoard tasks={filteredTasks} onEditTask={setEditingTask} />
      )}

      {/* Create form modal */}
      <TaskCreateForm
        open={showCreateForm}
        onClose={() => setShowCreateForm(false)}
      />

      {/* Edit form modal */}
      {editingTask && (
        <TaskEditForm
          open={!!editingTask}
          onClose={() => setEditingTask(null)}
          task={editingTask}
        />
      )}
    </div>
  );
}
