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
      <nldd-container layout="row" gap="12" vertical-alignment="top">
        {/* Checkbox */}
        <div onClick={(e) => e.stopPropagation()}>
          <NlddIconButton
            icon={isDone ? 'check-mark-circle' : 'circle'}
            variant="neutral-transparent"
            size="sm"
            accessibleLabel={isDone ? 'Markeer als niet afgerond' : 'Markeer als afgerond'}
            onClick={handleToggleDone}
          />
        </div>

        {/* Content */}
        <nldd-container width="full" gap="4">
          <nldd-text size="sm" weight="medium" color={isDone ? 'secondary' : 'content'}>
            {task.title}
          </nldd-text>

          {!compact && task.description && (
            <nldd-text size="xs" color="secondary">
              {richTextToPlain(task.description)}
            </nldd-text>
          )}

          <nldd-container layout="wrap" gap="8" vertical-alignment="center">
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
              <nldd-container layout="row" gap="4" vertical-alignment="center">
                <Icon name="clock" size="xs" />
                <nldd-text size="xs" color={isOverdue ? 'critical' : 'secondary'} weight={isOverdue ? 'bold' : 'regular'}>
                  {formatDateShort(task.due_date)}
                </nldd-text>
              </nldd-container>
            )}

            {task.assignee && (
              <nldd-container layout="row" gap="4" vertical-alignment="center">
                {task.assignee.is_agent ? (
                  <nldd-icon name="sparkles" size="16" color="paars" aria-hidden="true" />
                ) : (
                  <Icon name="person" size="xs" />
                )}
                <nldd-text size="xs" color="secondary">{task.assignee.naam}</nldd-text>
              </nldd-container>
            )}

            {task.organisatie_eenheid && (
              <nldd-container layout="row" gap="4" vertical-alignment="center">
                <Icon name="apartment-building" size="xs" />
                <nldd-text size="xs" color="secondary">{task.organisatie_eenheid.naam}</nldd-text>
              </nldd-container>
            )}

            {task.work_type && (
              <Badge variant="slate">{task.work_type}</Badge>
            )}

            {subtasks.length > 0 && (
              <nldd-container layout="row" gap="4" vertical-alignment="center">
                <Icon name="tree-structure" size="xs" />
                <nldd-text size="xs" color="secondary">{doneSubtasks}/{subtasks.length}</nldd-text>
              </nldd-container>
            )}
          </nldd-container>
        </nldd-container>
      </nldd-container>
    </Card>
  );
}
