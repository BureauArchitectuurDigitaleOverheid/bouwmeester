import { useState } from 'react';
import { TaskCard } from './TaskCard';
import { useUpdateTask } from '@/hooks/useTasks';
import { TaskStatus, TASK_STATUS_LABELS } from '@/types';
import type { Task } from '@/types';

interface TaskBoardProps {
  tasks: Task[];
  onEditTask: (task: Task) => void;
}

const BOARD_COLUMNS: TaskStatus[] = [
  TaskStatus.OPEN,
  TaskStatus.IN_PROGRESS,
  TaskStatus.DONE,
];

/** Column accent, using the semantic roles rather than literal colors. */
type NlddTagColor = NonNullable<React.ComponentProps<'nldd-tag'>['color']>;

const COLUMN_TAG_COLOR: Record<TaskStatus, NlddTagColor> = {
  [TaskStatus.OPEN]: 'accent',
  [TaskStatus.IN_PROGRESS]: 'warning',
  [TaskStatus.DONE]: 'success',
  [TaskStatus.CANCELLED]: 'neutral',
};

export function TaskBoard({ tasks, onEditTask }: TaskBoardProps) {
  const updateTask = useUpdateTask();
  const [dragOverColumn, setDragOverColumn] = useState<TaskStatus | null>(null);

  const tasksByStatus = BOARD_COLUMNS.reduce(
    (acc, status) => {
      acc[status] = tasks.filter((t) => t.status === status);
      return acc;
    },
    {} as Record<TaskStatus, Task[]>,
  );

  const handleDragStart = (e: React.DragEvent, task: Task) => {
    e.dataTransfer.setData('text/plain', task.id);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e: React.DragEvent, status: TaskStatus) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverColumn(status);
  };

  const handleDragLeave = () => {
    setDragOverColumn(null);
  };

  const handleDrop = (e: React.DragEvent, targetStatus: TaskStatus) => {
    e.preventDefault();
    setDragOverColumn(null);
    const taskId = e.dataTransfer.getData('text/plain');
    const task = tasks.find((t) => t.id === taskId);
    if (!task || task.status === targetStatus) return;

    updateTask.mutate({
      id: taskId,
      data: { status: targetStatus },
    });
  };

  return (
    <div className="-mx-4 px-4 md:mx-0 md:px-0 flex gap-4 min-h-[400px] overflow-x-auto pb-2 snap-x snap-mandatory md:grid md:grid-cols-3 md:overflow-x-visible md:snap-none md:pb-0">
      {BOARD_COLUMNS.map((status) => (
        <div
          key={status}
          onDragOver={(e) => handleDragOver(e, status)}
          onDragLeave={handleDragLeave}
          onDrop={(e) => handleDrop(e, status)}
          className={`rounded-xl border border-border bg-gray-50/50 w-[85vw] shrink-0 snap-center md:w-auto md:shrink md:flex-1 transition-colors ${
            dragOverColumn === status ? 'bg-primary-50/50 border-primary-200' : ''
          }`}
        >
          <div className="px-4 py-3 flex items-center justify-between">
            <nldd-text size="sm" weight="bold">
              {TASK_STATUS_LABELS[status]}
            </nldd-text>
            <nldd-badge color={COLUMN_TAG_COLOR[status]} number={tasksByStatus[status]?.length ?? 0} decorative />
          </div>

          <div className="px-3 pb-3 space-y-2 min-h-[100px]">
            {tasksByStatus[status]?.map((task) => (
              <div
                key={task.id}
                draggable
                onDragStart={(e) => handleDragStart(e, task)}
                className="cursor-grab active:cursor-grabbing"
              >
                <TaskCard task={task} onEdit={onEditTask} compact />
              </div>
            ))}

            {(tasksByStatus[status]?.length ?? 0) === 0 && (
              <div className="flex items-center justify-center h-[100px]">
                <nldd-text size="xs" color="secondary">
                  Sleep taken hierheen
                </nldd-text>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
