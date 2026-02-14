import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Calendar,
  Link as LinkIcon,
  Pencil,
  ExternalLink,
  Users,
  Tag as TagIcon,
  CheckCircle2,
  Circle,
  Clock,
  ArrowRight,
} from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { ReferencesList } from '@/components/common/ReferencesList';
import { NodeEditForm } from './NodeEditForm';
import { useNode, useNodeStakeholders, useNodeNeighbors, useNodeParlementairItem } from '@/hooks/useNodes';
import { useNodeTags } from '@/hooks/useTags';
import { useQuery } from '@tanstack/react-query';
import { getTasks } from '@/api/tasks';
import {
  NODE_TYPE_COLORS,
  NODE_STATUS_LABELS,
  STAKEHOLDER_ROL_LABELS,
  TASK_PRIORITY_COLORS,
  TaskStatus,
  type NodeStatus,
} from '@/types';
import type { Task } from '@/types';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { formatDateLong } from '@/utils/dates';

interface NodeDetailModalProps {
  nodeId: string | null;
  open: boolean;
  onClose: () => void;
}

export function NodeDetailModal({ nodeId, open, onClose }: NodeDetailModalProps) {
  const { data: node, isLoading } = useNode(nodeId ?? undefined);
  const { data: stakeholders } = useNodeStakeholders(nodeId ?? undefined);
  const { data: neighbors } = useNodeNeighbors(nodeId ?? undefined);
  const { data: nodeTags } = useNodeTags(nodeId ?? '');
  const { data: tasks } = useQuery({
    queryKey: ['tasks', 'list', { node_id: nodeId }],
    queryFn: () => getTasks({ node_id: nodeId! }),
    enabled: !!nodeId,
  });
  const { data: parlementairItem } = useNodeParlementairItem(
    nodeId ?? undefined,
    node?.node_type,
  );
  const [showEdit, setShowEdit] = useState(false);
  const navigate = useNavigate();
  const { nodeLabel, nodeAltLabel } = useVocabulary();
  const { openTaskDetail } = useTaskDetail();

  if (!open) return null;

  if (showEdit && node) {
    return (
      <NodeEditForm
        open
        onClose={() => {
          setShowEdit(false);
          onClose();
        }}
        node={node}
      />
    );
  }

  const eigenaren = stakeholders?.filter((s) => s.rol === 'eigenaar') ?? [];
  const otherStakeholders = stakeholders?.filter((s) => s.rol !== 'eigenaar') ?? [];

  const openTasks = tasks?.filter(
    (t) => t.status === TaskStatus.OPEN || t.status === TaskStatus.IN_PROGRESS,
  ) ?? [];
  const doneTasks = tasks?.filter(
    (t) => t.status === TaskStatus.DONE || t.status === TaskStatus.CANCELLED,
  ) ?? [];

  function taskIcon(task: Task) {
    if (task.status === TaskStatus.DONE) return <CheckCircle2 className="h-3.5 w-3.5 text-green-500 shrink-0" />;
    if (task.status === TaskStatus.IN_PROGRESS) return <Clock className="h-3.5 w-3.5 text-blue-500 shrink-0" />;
    return <Circle className="h-3.5 w-3.5 text-gray-400 shrink-0" />;
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isLoading ? 'Laden...' : node?.title ?? 'Node niet gevonden'}
      size="lg"
      footer={
        <div className="flex items-center justify-between w-full">
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              icon={<Pencil className="h-4 w-4" />}
              onClick={() => setShowEdit(true)}
              disabled={!node}
            >
              Bewerken
            </Button>
            <Button
              variant="secondary"
              size="sm"
              icon={<ExternalLink className="h-4 w-4" />}
              onClick={() => {
                onClose();
                navigate(`/nodes/${nodeId}`);
              }}
              disabled={!node}
            >
              Openen
            </Button>
          </div>
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
      ) : !node ? (
        <div className="flex items-center justify-center py-8 text-text-secondary text-sm">
          Node niet gevonden.
        </div>
      ) : (
        <div className="space-y-5">
          {/* Type, status, edge count badges */}
          <div className="flex items-center gap-3 flex-wrap">
            <Badge variant={NODE_TYPE_COLORS[node.node_type] ?? 'gray'} dot title={nodeAltLabel(node.node_type)}>
              {nodeLabel(node.node_type)}
            </Badge>
            {node.status && <Badge variant="gray">{NODE_STATUS_LABELS[node.status as NodeStatus] ?? node.status}</Badge>}
            {node.edge_count != null && (
              <span className="inline-flex items-center gap-1 text-sm text-text-secondary">
                <LinkIcon className="h-4 w-4" />
                {node.edge_count} verbindingen
              </span>
            )}
            {parlementairItem?.document_url && (
              <a
                href={parlementairItem.document_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-sm text-primary-700 hover:text-primary-900 transition-colors"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                tweedekamer.nl
              </a>
            )}
          </div>

          {/* Eigenaar / stakeholders compact row */}
          {stakeholders && stakeholders.length > 0 && (
            <div className="flex items-start gap-4">
              {eigenaren.length > 0 && (
                <div className="min-w-0">
                  <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1.5">
                    <Users className="h-3.5 w-3.5 inline mr-1 -mt-0.5" />
                    Eigenaar
                  </h4>
                  <div className="flex flex-wrap gap-1.5">
                    {eigenaren.map((s) => (
                      <span
                        key={s.id}
                        className="inline-flex items-center gap-1.5 rounded-full bg-primary-50 text-primary-800 px-2.5 py-1 text-sm font-medium"
                      >
                        {s.person.naam}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {otherStakeholders.length > 0 && (
                <div className="min-w-0">
                  <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1.5">
                    Betrokkenen
                  </h4>
                  <div className="flex flex-wrap gap-1.5">
                    {otherStakeholders.slice(0, 6).map((s) => (
                      <span
                        key={s.id}
                        className="inline-flex items-center gap-1 rounded-full bg-gray-100 text-gray-700 px-2.5 py-1 text-xs"
                      >
                        {s.person.naam}
                        <span className="text-gray-400">
                          ({STAKEHOLDER_ROL_LABELS[s.rol] ?? s.rol})
                        </span>
                      </span>
                    ))}
                    {otherStakeholders.length > 6 && (
                      <span className="inline-flex items-center rounded-full bg-gray-100 text-gray-500 px-2.5 py-1 text-xs">
                        +{otherStakeholders.length - 6}
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Tags */}
          {nodeTags && nodeTags.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1.5">
                <TagIcon className="h-3.5 w-3.5 inline mr-1 -mt-0.5" />
                Tags
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {nodeTags.map((nt) => (
                  <span
                    key={nt.id}
                    className="inline-flex items-center rounded-full bg-slate-100 text-slate-700 px-2.5 py-0.5 text-xs font-medium"
                  >
                    {nt.tag.name}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Description */}
          {node.description && (
            <div>
              <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
                Beschrijving
              </h4>
              <RichTextDisplay content={node.description} />
            </div>
          )}

          {/* Connected nodes */}
          {neighbors && neighbors.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
                <LinkIcon className="h-3.5 w-3.5 inline mr-1 -mt-0.5" />
                Verbonden nodes ({neighbors.length})
              </h4>
              <div className="space-y-1">
                {neighbors.slice(0, 8).map((neighbor) => (
                  <button
                    key={neighbor.id}
                    onClick={() => {
                      onClose();
                      navigate(`/nodes/${neighbor.id}`);
                    }}
                    className="flex items-center gap-2 w-full p-1.5 rounded-lg hover:bg-gray-50 transition-colors text-left group"
                  >
                    <Badge
                      variant={NODE_TYPE_COLORS[neighbor.node_type] ?? 'gray'}
                      dot
                      title={nodeAltLabel(neighbor.node_type)}
                    >
                      {nodeLabel(neighbor.node_type)}
                    </Badge>
                    <span className="text-sm text-text truncate group-hover:text-primary-700 transition-colors">
                      {neighbor.title}
                    </span>
                    <ArrowRight className="h-3.5 w-3.5 text-gray-300 shrink-0 ml-auto opacity-0 group-hover:opacity-100 transition-opacity" />
                  </button>
                ))}
                {neighbors.length > 8 && (
                  <button
                    onClick={() => {
                      onClose();
                      navigate(`/nodes/${nodeId}`);
                    }}
                    className="text-xs text-primary-700 hover:text-primary-900 transition-colors pl-1.5 pt-1"
                  >
                    Bekijk alle {neighbors.length} verbindingen
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Open tasks */}
          {tasks && tasks.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
                Taken
                <span className="ml-1.5 text-text-secondary font-normal normal-case">
                  {openTasks.length} open{doneTasks.length > 0 ? `, ${doneTasks.length} afgerond` : ''}
                </span>
              </h4>
              <div className="space-y-0.5">
                {openTasks.slice(0, 5).map((task) => (
                  <button
                    key={task.id}
                    onClick={() => openTaskDetail(task.id)}
                    className="flex items-center gap-2 w-full p-1.5 rounded-lg hover:bg-gray-50 transition-colors text-left group"
                  >
                    {taskIcon(task)}
                    <span className="text-sm text-text truncate group-hover:text-primary-700 transition-colors">
                      {task.title}
                    </span>
                    {task.priority && task.priority !== 'normaal' && (
                      <Badge variant={TASK_PRIORITY_COLORS[task.priority] ?? 'gray'}>
                        {task.priority}
                      </Badge>
                    )}
                    {task.assignee && (
                      <span className="text-xs text-text-secondary ml-auto shrink-0">
                        {task.assignee.naam}
                      </span>
                    )}
                  </button>
                ))}
                {openTasks.length > 5 && (
                  <button
                    onClick={() => {
                      onClose();
                      navigate(`/nodes/${nodeId}`);
                    }}
                    className="text-xs text-primary-700 hover:text-primary-900 transition-colors pl-1.5 pt-1"
                  >
                    Bekijk alle {openTasks.length} open taken
                  </button>
                )}
              </div>
            </div>
          )}

          {/* References */}
          <ReferencesList targetId={node.id} />

          {/* Metadata grid */}
          <div className="grid grid-cols-2 gap-4 text-sm border-t border-border pt-4">
            <div>
              <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                Aangemaakt
              </h4>
              <span className="inline-flex items-center gap-1.5 text-text-secondary">
                <Calendar className="h-4 w-4" />
                {formatDateLong(node.created_at)}
              </span>
            </div>

            <div>
              <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                Laatst bijgewerkt
              </h4>
              <span className="inline-flex items-center gap-1.5 text-text-secondary">
                <Calendar className="h-4 w-4" />
                {formatDateLong(node.updated_at)}
              </span>
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}
