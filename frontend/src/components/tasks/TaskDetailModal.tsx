import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Clock, User, Bot, Calendar, Link as LinkIcon, Pencil, Building2, ListTree, Plus, CheckCircle2, Circle, FileSearch } from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { ReferencesList } from '@/components/common/ReferencesList';
import { TaskEditForm } from './TaskEditForm';
import { TaskCreateForm } from './TaskCreateForm';
import { useTask } from '@/hooks/useTasks';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { isOverdue as checkOverdue, formatDateLong, formatDateShort } from '@/utils/dates';
import {
  TaskStatus,
  TASK_STATUS_LABELS,
  TASK_STATUS_COLORS,
  TASK_PRIORITY_LABELS,
  TASK_PRIORITY_COLORS,
} from '@/types';

interface TaskDetailModalProps {
  taskId: string | null;
  open: boolean;
  onClose: () => void;
}

export function TaskDetailModal({ taskId, open, onClose }: TaskDetailModalProps) {
  const { data: task, isLoading } = useTask(taskId);
  const [showEdit, setShowEdit] = useState(false);
  const [showSubtaskCreate, setShowSubtaskCreate] = useState(false);
  const { openNodeDetail } = useNodeDetail();
  const { openTaskDetail } = useTaskDetail();
  const navigate = useNavigate();

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
    checkOverdue(task.due_date) &&
    task.status !== TaskStatus.DONE;

  const subtasks = task?.subtasks ?? [];

  return (
    <>
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
              <Badge variant={TASK_STATUS_COLORS[task.status] ?? 'gray'} dot>
                {TASK_STATUS_LABELS[task.status]}
              </Badge>
              <Badge variant={TASK_PRIORITY_COLORS[task.priority] ?? 'gray'} dot>
                {TASK_PRIORITY_LABELS[task.priority]}
              </Badge>
              {task.due_date && (
                <span
                  className={`inline-flex items-center gap-1 text-sm ${
                    isOverdue ? 'text-red-600 font-medium' : 'text-text-secondary'
                  }`}
                >
                  <Clock className="h-4 w-4" />
                  {formatDateLong(task.due_date)}
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

              {/* Org unit */}
              <div>
                <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                  Verantwoordelijke eenheid
                </h4>
                {task.organisatie_eenheid ? (
                  <span className="inline-flex items-center gap-1.5 text-text">
                    <Building2 className="h-4 w-4 text-text-secondary" />
                    {task.organisatie_eenheid.naam}
                  </span>
                ) : (
                  <span className="text-text-secondary">Geen</span>
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
                    className="inline-flex items-start gap-1.5 text-primary-600 hover:text-primary-800 transition-colors text-left"
                  >
                    <LinkIcon className="h-4 w-4 shrink-0 mt-0.5" />
                    {task.node.title}
                  </button>
                ) : (
                  <span className="text-text-secondary">Geen</span>
                )}
              </div>

              {/* Parlementair review link */}
              {task.parlementair_item_id && (
                <div>
                  <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                    Beoordeling
                  </h4>
                  <button
                    onClick={() => {
                      onClose();
                      navigate(`/parlementair?item=${task.parlementair_item_id}`);
                    }}
                    className="inline-flex items-center gap-1.5 text-primary-600 hover:text-primary-800 transition-colors text-sm"
                  >
                    <FileSearch className="h-4 w-4" />
                    Ga naar beoordeling
                  </button>
                </div>
              )}

              {/* Created at */}
              <div>
                <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                  Aangemaakt
                </h4>
                <span className="inline-flex items-center gap-1.5 text-text-secondary">
                  <Calendar className="h-4 w-4" />
                  {formatDateLong(task.created_at)}
                </span>
              </div>
            </div>

            {/* Subtasks */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider flex items-center gap-1.5">
                  <ListTree className="h-3.5 w-3.5" />
                  Subtaken ({subtasks.length})
                </h4>
                <Button
                  variant="ghost"
                  size="sm"
                  icon={<Plus className="h-3.5 w-3.5" />}
                  onClick={() => setShowSubtaskCreate(true)}
                >
                  Subtaak toevoegen
                </Button>
              </div>
              {subtasks.length > 0 ? (
                <div className="space-y-1">
                  {subtasks.map((sub) => {
                    const subDone = sub.status === TaskStatus.DONE;
                    return (
                      <button
                        key={sub.id}
                        onClick={() => {
                          onClose();
                          openTaskDetail(sub.id);
                        }}
                        className="flex items-center gap-2 w-full px-3 py-2 rounded-lg hover:bg-gray-50 transition-colors text-left"
                      >
                        {subDone ? (
                          <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                        ) : (
                          <Circle className="h-4 w-4 text-text-secondary shrink-0" />
                        )}
                        <span className={`text-sm flex-1 ${subDone ? 'text-text-secondary line-through' : 'text-text'}`}>
                          {sub.title}
                        </span>
                        {sub.assignee && (
                          <span className="text-xs text-text-secondary">{sub.assignee.naam}</span>
                        )}
                        {sub.due_date && (
                          <span className="text-xs text-text-secondary">
                            {formatDateShort(sub.due_date)}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              ) : (
                <p className="text-sm text-text-secondary">Geen subtaken</p>
              )}
            </div>
          </div>
        )}
      </Modal>

      {/* Subtask create form */}
      {task && (
        <TaskCreateForm
          open={showSubtaskCreate}
          onClose={() => setShowSubtaskCreate(false)}
          nodeId={task.node_id}
          parentId={task.id}
        />
      )}
    </>
  );
}
