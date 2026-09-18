import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '@/components/nldd/Icon';
import { NlddIconButton } from '@/components/nldd/NlddIconButton';
import { Modal } from '@/components/common/Modal';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { ReferencesList } from '@/components/common/ReferencesList';
import { DetailSection } from '@/components/common/DetailSection';
import { DetailMetadataGrid } from '@/components/common/DetailMetadataGrid';
import { DetailModalFooter } from '@/components/common/DetailModalFooter';
import { TaskEditForm } from './TaskEditForm';
import { TaskCreateForm } from './TaskCreateForm';
import { useTask, useReorderSubtasks } from '@/hooks/useTasks';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { useOpdrachtDetail } from '@/contexts/OpdrachtDetailContext';
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
  zIndex?: number;
}

export function TaskDetailModal({ taskId, open, onClose, zIndex }: TaskDetailModalProps) {
  const { data: task, isLoading } = useTask(taskId);
  const [showEdit, setShowEdit] = useState(false);
  const [showSubtaskCreate, setShowSubtaskCreate] = useState(false);
  const { openNodeDetail } = useNodeDetail();
  const { openOpdrachtDetail } = useOpdrachtDetail();
  const { openTaskDetail, taskParentLabel } = useTaskDetail();
  const navigate = useNavigate();
  const reorderSubtasks = useReorderSubtasks();

  const handleMoveSubtask = (index: number, direction: 'up' | 'down') => {
    if (!task) return;
    const subs = [...(task.subtasks ?? [])];
    const newIndex = direction === 'up' ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= subs.length) return;
    [subs[index], subs[newIndex]] = [subs[newIndex], subs[index]];
    reorderSubtasks.mutate({ taskId: task.id, taskIds: subs.map((s) => s.id) });
  };

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
  const accentColor = task ? TASK_STATUS_COLORS[task.status] : undefined;

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={isLoading ? 'Laden...' : task?.title ?? 'Taak niet gevonden'}
        size="lg"
        zIndex={zIndex}
        accentColor={accentColor}
        headerIcon={<Icon name="check-list" size="md" />}
        entityLabel="Taak"
        backLabel={taskParentLabel ?? undefined}
        onBack={taskParentLabel ? onClose : undefined}
        footer={
          <DetailModalFooter
            onClose={onClose}
            actions={
              <Button
                variant="secondary"
                size="sm"
                icon="pencil"
                onClick={() => setShowEdit(true)}
                disabled={!task}
              >
                Bewerken
              </Button>
            }
          />
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
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant={TASK_STATUS_COLORS[task.status] ?? 'gray'} dot>
                {TASK_STATUS_LABELS[task.status]}
              </Badge>
              <Badge variant={TASK_PRIORITY_COLORS[task.priority] ?? 'gray'} dot>
                {TASK_PRIORITY_LABELS[task.priority]}
              </Badge>
              {task.due_date && (
                <span
                  className={`inline-flex items-center gap-1 text-sm ${
                    isOverdue
                      ? 'text-red-600 font-medium bg-red-50 rounded-md px-2 py-0.5'
                      : 'text-text-secondary'
                  }`}
                >
                  <Icon name="clock" size="md" />
                  {formatDateLong(task.due_date)}
                </span>
              )}
            </div>

            {/* Description */}
            <DetailSection title="Beschrijving">
              <RichTextDisplay content={task.description} />
            </DetailSection>

            {/* References */}
            <ReferencesList targetId={task.id} />

            {/* Metadata grid */}
            <DetailMetadataGrid
              items={[
                {
                  label: 'Toegewezen aan',
                  value: task.assignee ? (
                    <span className="inline-flex items-center gap-1.5 text-text">
                      {task.assignee.is_agent ? (
                        <Icon name="sparkles" size="md" className="text-violet-500" />
                      ) : (
                        <Icon name="person" size="md" />
                      )}
                      {task.assignee.naam}
                    </span>
                  ) : (
                    <span className="text-text-secondary">Niet toegewezen</span>
                  ),
                },
                {
                  label: 'Verantwoordelijke eenheid',
                  value: task.organisatie_eenheid ? (
                    <span className="inline-flex items-center gap-1.5 text-text">
                      <Icon name="apartment-building" size="md" />
                      {task.organisatie_eenheid.naam}
                    </span>
                  ) : (
                    <span className="text-text-secondary">Geen</span>
                  ),
                },
                {
                  label: 'Node',
                  value: task.node ? (
                    <button
                      onClick={() => openNodeDetail(task.node_id!, task.title)}
                      className="inline-flex items-start gap-1.5 text-primary-600 hover:text-primary-800 hover:underline transition-colors text-left"
                    >
                      <Icon name="link" size="md" className="shrink-0 mt-0.5" />
                      {task.node.title}
                    </button>
                  ) : (
                    <span className="text-text-secondary">Geen</span>
                  ),
                },
                ...(task.opdracht
                  ? [
                      {
                        label: 'Opdracht',
                        value: (
                          <button
                            onClick={() => openOpdrachtDetail(task.opdracht!.id, task.title)}
                            className="inline-flex items-center gap-1.5 text-primary-600 hover:text-primary-800 hover:underline transition-colors text-sm text-left"
                          >
                            <Icon name="clipboard-bullet-list" size="md" className="shrink-0" />
                            {task.opdracht!.titel}
                          </button>
                        ),
                      },
                    ]
                  : []),
                ...(task.parlementair_item_id
                  ? [
                      {
                        label: 'Beoordeling',
                        value: (
                          <button
                            onClick={() => {
                              onClose();
                              navigate(`/parlementair?item=${task.parlementair_item_id}`);
                            }}
                            className="inline-flex items-center gap-1.5 text-primary-600 hover:text-primary-800 hover:underline transition-colors text-sm"
                          >
                            <Icon name="file-text" size="md" />
                            Ga naar beoordeling
                          </button>
                        ),
                      },
                    ]
                  : []),
                {
                  label: 'Aangemaakt',
                  value: formatDateLong(task.created_at),
                  icon: <Icon name="calendar" size="md" />,
                },
              ]}
            />

            {/* Subtasks */}
            <DetailSection
              title="Subtaken"
              icon={<Icon name="tree-structure" size="sm" />}
              count={subtasks.length}
              action={
                <Button
                  variant="ghost"
                  size="sm"
                  icon="plus"
                  onClick={() => setShowSubtaskCreate(true)}
                >
                  Subtaak toevoegen
                </Button>
              }
            >
              {subtasks.length > 0 ? (
                <div className="space-y-1">
                  {subtasks.map((sub, idx) => {
                    const subDone = sub.status === TaskStatus.DONE;
                    return (
                      <div
                        key={sub.id}
                        className="flex items-center gap-1 w-full"
                      >
                        <div className="flex flex-col shrink-0">
                          <NlddIconButton
                            icon="chevron-up"
                            variant="neutral-transparent"
                            size="xs"
                            accessibleLabel="Omhoog"
                            disabled={idx === 0 || reorderSubtasks.isPending}
                            onClick={() => handleMoveSubtask(idx, 'up')}
                          />
                          <NlddIconButton
                            icon="chevron-down"
                            variant="neutral-transparent"
                            size="xs"
                            accessibleLabel="Omlaag"
                            disabled={idx === subtasks.length - 1 || reorderSubtasks.isPending}
                            onClick={() => handleMoveSubtask(idx, 'down')}
                          />
                        </div>
                        <button
                          onClick={() => openTaskDetail(sub.id, task.title)}
                          className="flex items-center gap-2 flex-1 min-w-0 px-2 py-2 rounded-lg hover:bg-gray-50 transition-colors text-left"
                        >
                          {subDone ? (
                            <Icon name="check-mark-circle" size="md" className="text-emerald-500 shrink-0" />
                          ) : (
                            <Icon name="circle" size="md" className="text-text-secondary shrink-0" />
                          )}
                          <span className={`text-sm flex-1 ${subDone ? 'text-text-secondary line-through' : 'text-text'}`}>
                            {sub.title}
                          </span>
                          {sub.work_type && (
                            <Badge variant="slate">{sub.work_type}</Badge>
                          )}
                          {sub.assignee && (
                            <span className="text-xs text-text-secondary">{sub.assignee.naam}</span>
                          )}
                          {sub.due_date && (
                            <span className="text-xs text-text-secondary">
                              {formatDateShort(sub.due_date)}
                            </span>
                          )}
                        </button>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-sm text-text-secondary">Geen subtaken</p>
              )}
            </DetailSection>
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
