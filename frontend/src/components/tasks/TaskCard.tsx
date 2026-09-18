import { Badge } from '@/components/common/Badge';
import { Card } from '@/components/common/Card';
import { Icon } from '@/components/nldd/Icon';
import { NlddIconButton } from '@/components/nldd/NlddIconButton';
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
  [TaskPriority.KRITIEK]: <Icon name="exclamation-triangle" size="sm" />,
  [TaskPriority.HOOG]: <Icon name="exclamation-triangle" size="sm" />,
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

  const handleToggleDone = () => {
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
        <div className="mt-0.5 shrink-0" onClick={(e) => e.stopPropagation()}>
          <NlddIconButton
            icon={isDone ? 'check-mark-circle' : 'circle'}
            variant="neutral-transparent"
            size="sm"
            accessibleLabel={isDone ? 'Markeer als niet afgerond' : 'Markeer als afgerond'}
            onClick={handleToggleDone}
          />
        </div>

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
                <Icon name="clock" size="xs" />
                {formatDateShort(task.due_date)}
              </span>
            )}

            {task.assignee && (
              <span className="inline-flex items-center gap-1 text-xs text-text-secondary">
                {task.assignee.is_agent ? (
                  <Icon name="sparkles" size="xs" className="text-violet-500" />
                ) : (
                  <Icon name="person" size="xs" />
                )}
                {task.assignee.naam}
              </span>
            )}

            {task.organisatie_eenheid && (
              <span className="inline-flex items-center gap-1 text-xs text-text-secondary">
                <Icon name="apartment-building" size="xs" />
                {task.organisatie_eenheid.naam}
              </span>
            )}

            {task.work_type && (
              <Badge variant="slate">{task.work_type}</Badge>
            )}

            {subtasks.length > 0 && (
              <span className="inline-flex items-center gap-1 text-xs text-text-secondary">
                <Icon name="tree-structure" size="xs" />
                {doneSubtasks}/{subtasks.length}
              </span>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
