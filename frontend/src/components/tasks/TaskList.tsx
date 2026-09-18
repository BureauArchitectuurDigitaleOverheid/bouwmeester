import { TaskCard } from './TaskCard';
import { EmptyState } from '@/components/common/EmptyState';
import { TaskStatus, TASK_STATUS_LABELS } from '@/types';
import type { Task } from '@/types';

interface TaskListProps {
  tasks: Task[];
  onEditTask: (task: Task) => void;
}

export function TaskList({ tasks, onEditTask }: TaskListProps) {
  if (tasks.length === 0) {
    return (
      <EmptyState
        icon="check-list"
        title="Geen taken gevonden"
        description="Er zijn geen taken die voldoen aan de huidige filters."
      />
    );
  }

  // Group tasks by status
  const groupedTasks = tasks.reduce(
    (groups, task) => {
      const key = task.status;
      if (!groups[key]) groups[key] = [];
      groups[key].push(task);
      return groups;
    },
    {} as Record<string, Task[]>,
  );

  // Show in logical order
  const statusOrder = [
    TaskStatus.OPEN,
    TaskStatus.IN_PROGRESS,
    TaskStatus.DONE,
    TaskStatus.CANCELLED,
  ];

  return (
    <div className="space-y-6">
      {statusOrder.map((status) => {
        const groupTasks = groupedTasks[status];
        if (!groupTasks || groupTasks.length === 0) return null;

        return (
          <div key={status}>
            <div className="mb-2 uppercase tracking-wider">
              <nldd-text size="xs" weight="bold" color="secondary">
                {TASK_STATUS_LABELS[status]} ({groupTasks.length})
              </nldd-text>
            </div>
            <div className="space-y-2">
              {groupTasks.map((task) => (
                <TaskCard key={task.id} task={task} onEdit={onEditTask} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
