import { CheckCircle2, Circle, Clock, AlertTriangle, User, Bot, Building2, ListTree } from 'lucide-react';
import { Badge } from '@/components/common/Badge';
import { Card } from '@/components/common/Card';
import { useUpdateTask } from '@/hooks/useTasks';
import {
  TaskStatus,
  TaskPriority,
  TASK_PRIORITY_LABELS,
  TASK_PRIORITY_COLORS,
  TASK_STATUS_LABELS,
} from '@/types';
import type { Task } from '@/types';
import { richTextToPlain } from '@/utils/richtext';
import { isOverdue as checkOverdue, formatDateShort } from '@/utils/dates';

interface TaskCardProps {
  task: Task;
  onEdit?: (task: Task) => void;
  compact?: boolean;
}

const priorityIcons: Record<TaskPriority, React.ReactNode> = {
  [TaskPriority.KRITIEK]: <AlertTriangle className="h-3.5 w-3.5" />,
  [TaskPriority.HOOG]: <AlertTriangle className="h-3.5 w-3.5" />,
  [TaskPriority.NORMAAL]: null,
  [TaskPriority.LAAG]: null,
};

export function TaskCard({ task, onEdit, compact = false }: TaskCardProps) {
  const updateTask = useUpdateTask();
  const isDone = task.status === TaskStatus.DONE;
  const isOverdue =
    task.due_date && checkOverdue(task.due_date) && !isDone;

  const subtasks = task.subtasks ?? [];
  const doneSubtasks = subtasks.filter((s) => s.status === TaskStatus.DONE).length;

  const handleToggleDone = (e: React.MouseEvent) => {
    e.stopPropagation();
    updateTask.mutate({
      id: task.id,
      data: {
        status: isDone ? TaskStatus.OPEN : TaskStatus.DONE,
      },
    });
  };

  const handleCardClick = () => {
    onEdit?.(task);
  };

  return (
    <Card
      hoverable={!!onEdit}
      onClick={onEdit ? handleCardClick : undefined}
    >
      <div className="flex items-start gap-3">
        {/* Checkbox */}
        <button
          onClick={handleToggleDone}
          className={`mt-0.5 shrink-0 transition-colors ${
            isDone
              ? 'text-emerald-500 hover:text-emerald-600'
              : 'text-text-secondary hover:text-primary-700'
          }`}
        >
          {isDone ? (
            <CheckCircle2 className="h-5 w-5" />
          ) : (
            <Circle className="h-5 w-5" />
          )}
        </button>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <p
            className={`text-sm font-medium ${
              isDone ? 'text-text-secondary line-through' : 'text-text'
            }`}
          >
            {task.title}
          </p>

          {!compact && task.description && (
            <p className="text-xs text-text-secondary mt-0.5 line-clamp-1">
              {richTextToPlain(task.description)}
            </p>
          )}

          <div className="flex items-center gap-2 mt-2 flex-wrap">
            <Badge
              variant={TASK_PRIORITY_COLORS[task.priority]}
              dot
            >
              {priorityIcons[task.priority]}
              {TASK_PRIORITY_LABELS[task.priority]}
            </Badge>

            {!compact && (
              <Badge variant={isDone ? 'green' : 'gray'}>
                {TASK_STATUS_LABELS[task.status]}
              </Badge>
            )}

            {task.due_date && (
              <span
                className={`inline-flex items-center gap-1 text-xs ${
                  isOverdue ? 'text-red-600 font-medium' : 'text-text-secondary'
                }`}
              >
                <Clock className="h-3 w-3" />
                {formatDateShort(task.due_date)}
              </span>
            )}

            {task.assignee && (
              <span className="inline-flex items-center gap-1 text-xs text-text-secondary">
                {task.assignee.is_agent ? (
                  <Bot className="h-3 w-3 text-violet-500" />
                ) : (
                  <User className="h-3 w-3" />
                )}
                {task.assignee.naam}
              </span>
            )}

            {task.organisatie_eenheid && (
              <span className="inline-flex items-center gap-1 text-xs text-text-secondary">
                <Building2 className="h-3 w-3" />
                {task.organisatie_eenheid.naam}
              </span>
            )}

            {subtasks.length > 0 && (
              <span className="inline-flex items-center gap-1 text-xs text-text-secondary">
                <ListTree className="h-3 w-3" />
                {doneSubtasks}/{subtasks.length}
              </span>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
