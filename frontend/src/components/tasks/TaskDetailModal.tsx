import { useState } from 'react';
import { Clock, User, Bot, Calendar, Link as LinkIcon, Pencil } from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { ReferencesList } from '@/components/common/ReferencesList';
import { TaskEditForm } from './TaskEditForm';
import { useTask } from '@/hooks/useTasks';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import {
  TASK_STATUS_LABELS,
  TASK_PRIORITY_LABELS,
  TASK_PRIORITY_COLORS,
  TaskStatus,
} from '@/types';

interface TaskDetailModalProps {
  taskId: string | null;
  open: boolean;
  onClose: () => void;
}

const STATUS_COLORS: Record<string, string> = {
  [TaskStatus.OPEN]: 'blue',
  [TaskStatus.IN_PROGRESS]: 'amber',
  [TaskStatus.DONE]: 'green',
  [TaskStatus.CANCELLED]: 'gray',
};

export function TaskDetailModal({ taskId, open, onClose }: TaskDetailModalProps) {
  const { data: task, isLoading } = useTask(taskId);
  const [showEdit, setShowEdit] = useState(false);
  const { openNodeDetail } = useNodeDetail();

  if (!open) return null;

  if (showEdit && task) {
    return (
      <TaskEditForm
        open
        onClose={() => {
          setShowEdit(false);
          onClose();
        }}
        task={task}
      />
    );
  }

  const isOverdue =
    task?.due_date &&
    new Date(task.due_date) < new Date() &&
    task.status !== TaskStatus.DONE;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isLoading ? 'Laden...' : task?.title ?? 'Taak niet gevonden'}
      size="lg"
      footer={
        <div className="flex items-center justify-between w-full">
          <Button
            variant="secondary"
            size="sm"
            icon={<Pencil className="h-4 w-4" />}
            onClick={() => setShowEdit(true)}
            disabled={!task}
          >
            Bewerken
          </Button>
          <Button variant="secondary" onClick={onClose}>
            Sluiten
          </Button>
        </div>
      }
    >
      {isLoading ? (
        <div className="flex items-center justify-center py-8 text-text-secondary text-sm">
          Laden...
        </div>
      ) : !task ? (
        <div className="flex items-center justify-center py-8 text-text-secondary text-sm">
          Taak niet gevonden.
        </div>
      ) : (
        <div className="space-y-5">
          {/* Status / Priority / Deadline row */}
          <div className="flex items-center gap-3 flex-wrap">
            <Badge variant={(STATUS_COLORS[task.status] ?? 'gray') as 'blue'} dot>
              {TASK_STATUS_LABELS[task.status]}
            </Badge>
            <Badge variant={(TASK_PRIORITY_COLORS[task.priority] ?? 'gray') as 'blue'} dot>
              {TASK_PRIORITY_LABELS[task.priority]}
            </Badge>
            {task.due_date && (
              <span
                className={`inline-flex items-center gap-1 text-sm ${
                  isOverdue ? 'text-red-600 font-medium' : 'text-text-secondary'
                }`}
              >
                <Clock className="h-4 w-4" />
                {new Date(task.due_date).toLocaleDateString('nl-NL', {
                  day: 'numeric',
                  month: 'long',
                  year: 'numeric',
                })}
              </span>
            )}
          </div>

          {/* Description */}
          <div>
            <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
              Beschrijving
            </h4>
            <RichTextDisplay content={task.description} />
          </div>

          {/* References */}
          <ReferencesList targetId={task.id} />

          {/* Metadata grid */}
          <div className="grid grid-cols-2 gap-4 text-sm">
            {/* Assignee */}
            <div>
              <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                Toegewezen aan
              </h4>
              {task.assignee ? (
                <span className="inline-flex items-center gap-1.5 text-text">
                  {task.assignee.is_agent ? (
                    <Bot className="h-4 w-4 text-violet-500" />
                  ) : (
                    <User className="h-4 w-4 text-text-secondary" />
                  )}
                  {task.assignee.naam}
                </span>
              ) : (
                <span className="text-text-secondary">Niet toegewezen</span>
              )}
            </div>

            {/* Node */}
            <div>
              <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                Node
              </h4>
              {task.node ? (
                <button
                  onClick={() => {
                    onClose();
                    openNodeDetail(task.node_id!);
                  }}
                  className="inline-flex items-center gap-1.5 text-primary-600 hover:text-primary-800 transition-colors"
                >
                  <LinkIcon className="h-4 w-4" />
                  {task.node.title}
                </button>
              ) : (
                <span className="text-text-secondary">Geen</span>
              )}
            </div>

            {/* Created at */}
            <div>
              <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                Aangemaakt
              </h4>
              <span className="inline-flex items-center gap-1.5 text-text-secondary">
                <Calendar className="h-4 w-4" />
                {new Date(task.created_at).toLocaleDateString('nl-NL', {
                  day: 'numeric',
                  month: 'long',
                  year: 'numeric',
                })}
              </span>
            </div>

            {/* Updated at */}
            <div>
              <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                Laatst bijgewerkt
              </h4>
              <span className="inline-flex items-center gap-1.5 text-text-secondary">
                <Calendar className="h-4 w-4" />
                {task.updated_at && new Date(task.updated_at).getFullYear() > 2000
                  ? new Date(task.updated_at).toLocaleDateString('nl-NL', {
                      day: 'numeric',
                      month: 'long',
                      year: 'numeric',
                    })
                  : 'Nog niet bewerkt'}
              </span>
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}
