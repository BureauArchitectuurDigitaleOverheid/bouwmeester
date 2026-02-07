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

const COLUMN_COLORS: Record<TaskStatus, string> = {
  [TaskStatus.OPEN]: 'border-t-blue-400',
  [TaskStatus.IN_PROGRESS]: 'border-t-amber-400',
  [TaskStatus.DONE]: 'border-t-emerald-400',
  [TaskStatus.CANCELLED]: 'border-t-gray-400',
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
    <div className="grid grid-cols-3 gap-4 min-h-[400px]">
      {BOARD_COLUMNS.map((status) => (
        <div
          key={status}
          onDragOver={(e) => handleDragOver(e, status)}
          onDragLeave={handleDragLeave}
          onDrop={(e) => handleDrop(e, status)}
          className={`rounded-xl border border-border bg-gray-50/50 border-t-4 ${COLUMN_COLORS[status]} transition-colors ${
            dragOverColumn === status ? 'bg-primary-50/50 border-primary-200' : ''
          }`}
        >
          <div className="px-4 py-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-text">
              {TASK_STATUS_LABELS[status]}
            </h3>
            <span className="text-xs text-text-secondary bg-white rounded-full px-2 py-0.5 border border-border">
              {tasksByStatus[status]?.length ?? 0}
            </span>
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
              <div className="flex items-center justify-center h-[100px] text-xs text-text-secondary">
                Sleep taken hierheen
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
