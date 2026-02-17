import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
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
  FolderOpen,
  Target,
  Wrench,
  BookOpen,
  Shield,
  Landmark,
  AlertTriangle,
  TrendingUp,
  GitBranch,
  FileText,
} from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { ReferencesList } from '@/components/common/ReferencesList';
import { DetailSection } from '@/components/common/DetailSection';
import { DetailMetadataGrid } from '@/components/common/DetailMetadataGrid';
import { RelatedItemsList } from '@/components/common/RelatedItemsList';
import { DetailModalFooter } from '@/components/common/DetailModalFooter';
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
  type NodeType,
  type NodeStatus,
} from '@/types';
import type { Task } from '@/types';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { formatDateLong } from '@/utils/dates';

const NODE_TYPE_ICONS: Record<string, React.ReactNode> = {
  dossier: <FolderOpen className="h-5 w-5" />,
  doel: <Target className="h-5 w-5" />,
  instrument: <Wrench className="h-5 w-5" />,
  beleidskader: <BookOpen className="h-5 w-5" />,
  maatregel: <Shield className="h-5 w-5" />,
  politieke_input: <Landmark className="h-5 w-5" />,
  probleem: <AlertTriangle className="h-5 w-5" />,
  effect: <TrendingUp className="h-5 w-5" />,
  beleidsoptie: <GitBranch className="h-5 w-5" />,
  bron: <FileText className="h-5 w-5" />,
};

interface NodeDetailModalProps {
  nodeId: string | null;
  open: boolean;
  onClose: () => void;
  zIndex?: number;
}

export function NodeDetailModal({ nodeId, open, onClose, zIndex }: NodeDetailModalProps) {
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
  const location = useLocation();
  const { nodeLabel, nodeAltLabel } = useVocabulary();
  const { openTaskDetail } = useTaskDetail();
  const { openNodeDetail, nodeParentLabel } = useNodeDetail();

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

  const accentColor = node ? NODE_TYPE_COLORS[node.node_type as NodeType] : undefined;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isLoading ? 'Laden...' : node?.title ?? 'Node niet gevonden'}
      size="lg"
      zIndex={zIndex}
      accentColor={accentColor}
      headerIcon={node ? NODE_TYPE_ICONS[node.node_type] : undefined}
      entityLabel={node ? nodeLabel(node.node_type) : undefined}
      backLabel={nodeParentLabel ?? undefined}
      onBack={nodeParentLabel ? onClose : undefined}
      footer={
        <DetailModalFooter
          onClose={onClose}
          actions={
            <>
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
                  navigate(`/nodes/${nodeId}`, { state: { fromCorpus: location.pathname + location.search } });
                }}
                disabled={!node}
              >
                Openen
              </Button>
            </>
          }
        />
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
            <DetailSection title="Beschrijving">
              <RichTextDisplay content={node.description} />
            </DetailSection>
          )}

          {/* Connected nodes */}
          {neighbors && neighbors.length > 0 && (
            <DetailSection
              title="Verbonden nodes"
              icon={<LinkIcon className="h-3.5 w-3.5" />}
              count={neighbors.length}
            >
              <RelatedItemsList
                items={neighbors.map((neighbor) => ({
                  id: neighbor.id,
                  label: neighbor.title,
                  badge: {
                    text: nodeLabel(neighbor.node_type),
                    variant: NODE_TYPE_COLORS[neighbor.node_type] ?? 'gray',
                    dot: true,
                  },
                  onClick: () => openNodeDetail(neighbor.id, node.title),
                }))}
                maxVisible={5}
                onShowAll={() => {
                  onClose();
                  navigate(`/nodes/${nodeId}`, { state: { fromCorpus: location.pathname + location.search } });
                }}
                showAllLabel={`Bekijk alle ${neighbors.length} verbindingen`}
              />
            </DetailSection>
          )}

          {/* Tasks */}
          {tasks && tasks.length > 0 && (
            <DetailSection
              title="Taken"
              count={openTasks.length}
            >
              <div className="space-y-0.5">
                {openTasks.slice(0, 5).map((task) => (
                  <button
                    key={task.id}
                    onClick={() => openTaskDetail(task.id, node.title)}
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
                      navigate(`/nodes/${nodeId}`, { state: { fromCorpus: location.pathname + location.search } });
                    }}
                    className="text-xs text-primary-700 hover:text-primary-900 transition-colors pl-1.5 pt-1"
                  >
                    Bekijk alle {openTasks.length} open taken
                  </button>
                )}
                {doneTasks.length > 0 && (
                  <p className="text-xs text-text-secondary pl-1.5 pt-1">
                    {doneTasks.length} afgerond
                  </p>
                )}
              </div>
            </DetailSection>
          )}

          {/* References */}
          <ReferencesList targetId={node.id} />

          {/* Metadata footer */}
          <DetailMetadataGrid
            separated
            items={[
              {
                label: 'Aangemaakt',
                value: formatDateLong(node.created_at),
                icon: <Calendar className="h-4 w-4" />,
              },
              {
                label: 'Laatst bijgewerkt',
                value: formatDateLong(node.updated_at),
                icon: <Calendar className="h-4 w-4" />,
              },
            ]}
          />
        </div>
      )}
    </Modal>
  );
}
